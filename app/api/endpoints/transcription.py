import os
import uuid
import aiofiles
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from app.models.schemas import TranscriptionResponse, TranscriptionResult, JobStatusResponse
from app.core.redis_queue import job_queue
from app.core.whisper_service import whisper_service
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


async def process_transcription_job(job_id: str, file_path: str):
    """
    Función background para procesar transcripción
    Usa exactamente tu lógica de transcripción optimizada
    """
    try:
        logger.info(f"Iniciando procesamiento del trabajo {job_id}")

        # Transcribir usando tu servicio optimizado
        result = whisper_service.transcribe_audio(file_path)

        # Completar trabajo con éxito
        job_queue.complete_job(job_id, result, success=True)

        logger.info(f"Trabajo {job_id} completado exitosamente")

    except Exception as e:
        logger.error(f"Error procesando trabajo {job_id}: {e}")

        # Marcar trabajo como fallido
        job_queue.complete_job(job_id, {"error": str(e)}, success=False)

    finally:
        # Limpiar archivo temporal
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Archivo temporal eliminado: {file_path}")
        except Exception as e:
            logger.warning(f"No se pudo eliminar archivo temporal {file_path}: {e}")


@router.post("/transcribe", response_model=TranscriptionResponse)
async def create_transcription(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Subir archivo de audio para transcripción

    - **file**: Archivo de audio (mp3, wav, m4a, flac, ogg)
    - Returns: ID del trabajo y estado inicial
    """

    # === VALIDACIONES ===

    # Validar extensión de archivo
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado. Formatos permitidos: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )

    # Validar tamaño de archivo
    if file.size and file.size > settings.MAX_FILE_SIZE:
        size_mb = file.size / (1024 * 1024)
        max_mb = settings.MAX_FILE_SIZE / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"Archivo muy grande ({size_mb:.1f}MB). Tamaño máximo: {max_mb:.0f}MB"
        )

    # Validar disponibilidad del sistema
    if whisper_service.get_available_models_count() == 0:
        current_stats = job_queue.get_queue_stats()
        raise HTTPException(
            status_code=503,
            detail=f"Sistema ocupado. Trabajos en proceso: {current_stats['processing']}/{settings.MAX_CONCURRENT_JOBS}"
        )

    # === PROCESAMIENTO ===

    # Generar ID único para el trabajo
    job_id = str(uuid.uuid4())

    try:
        # Guardar archivo temporal
        temp_filename = f"{job_id}{file_extension}"
        temp_path = os.path.join(settings.UPLOAD_DIR, temp_filename)

        # Leer y guardar archivo de forma asíncrona
        content = await file.read()
        async with aiofiles.open(temp_path, 'wb') as f:
            await f.write(content)

        # Preparar datos del trabajo
        job_data = {
            "filename": file.filename,
            "file_path": temp_path,
            "file_size": len(content),
            "file_extension": file_extension
        }

        # Agregar trabajo a la cola Redis
        queue_position = job_queue.add_job(job_id, job_data)

        # Agregar tarea background para procesamiento
        background_tasks.add_task(process_transcription_job, job_id, temp_path)

        # Calcular tiempo estimado de espera
        stats = job_queue.get_queue_stats()
        avg_speed = stats.get("average_speed", 20)  # Default 20x como tu script
        estimated_minutes = max(1, queue_position * 2)  # Estimación conservadora
        estimated_wait = f"~{estimated_minutes} min" if queue_position > 0 else "procesando pronto"

        logger.info(f"Trabajo {job_id} creado para archivo '{file.filename}' (posición {queue_position})")

        return TranscriptionResponse(
            job_id=job_id,
            status="pending",
            queue_position=queue_position,
            estimated_wait_time=estimated_wait,
            message=f"Archivo '{file.filename}' agregado a la cola"
        )

    except Exception as e:
        logger.error(f"Error creando trabajo de transcripción: {e}")

        # Limpiar archivo temporal si se creó
        try:
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.remove(temp_path)
        except:
            pass

        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_transcription_status(job_id: str):
    """
    Obtener estado actual de un trabajo de transcripción

    - **job_id**: ID del trabajo
    - Returns: Estado actual y información del progreso
    """

    # Obtener datos del trabajo
    job_data = job_queue.get_job(job_id)
    if not job_data:
        raise HTTPException(
            status_code=404,
            detail=f"Trabajo {job_id} no encontrado"
        )

    response_data = {
        "job_id": job_id,
        "status": job_data.get("status"),
        "filename": job_data.get("filename"),
        "created_at": job_data.get("created_at"),
        "started_at": job_data.get("started_at")
    }

    # Si está pendiente, agregar posición en cola
    if job_data.get("status") == "pending":
        queue_position = job_queue.get_job_position(job_id)
        if queue_position:
            response_data["queue_position"] = queue_position
            response_data["message"] = f"En cola, posición {queue_position}"
        else:
            response_data["message"] = "Preparando para procesar"

    elif job_data.get("status") == "processing":
        response_data["message"] = "Transcribiendo audio..."

    elif job_data.get("status") == "completed":
        response_data["message"] = "Transcripción completada"

    elif job_data.get("status") == "failed":
        response_data["message"] = f"Error: {job_data.get('error', 'Error desconocido')}"

    return JobStatusResponse(**response_data)


@router.get("/result/{job_id}", response_model=TranscriptionResult)
async def get_transcription_result(job_id: str):
    """
    Obtener resultado completo de una transcripción

    - **job_id**: ID del trabajo
    - Returns: Texto transcrito y métricas de rendimiento
    """

    # Obtener datos del trabajo
    job_data = job_queue.get_job(job_id)
    if not job_data:
        raise HTTPException(
            status_code=404,
            detail=f"Trabajo {job_id} no encontrado"
        )

    # Si no está completado, devolver estado actual
    if job_data.get("status") != "completed":
        if job_data.get("status") == "failed":
            raise HTTPException(
                status_code=400,
                detail=f"Trabajo falló: {job_data.get('error', 'Error desconocido')}"
            )
        else:
            raise HTTPException(
                status_code=202,  # Accepted - still processing
                detail=f"Trabajo aún en estado: {job_data.get('status')}"
            )

    # Devolver resultado completo
    return TranscriptionResult(
        **job_data
    )


@router.delete("/job/{job_id}")
async def delete_transcription_job(job_id: str):
    """
    Eliminar un trabajo de transcripción

    - **job_id**: ID del trabajo a eliminar
    - Returns: Confirmación de eliminación
    """

    # Verificar que el trabajo existe
    job_data = job_queue.get_job(job_id)
    if not job_data:
        raise HTTPException(
            status_code=404,
            detail=f"Trabajo {job_id} no encontrado"
        )

    # No permitir eliminar trabajos en proceso
    if job_data.get("status") == "processing":
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar un trabajo que se está procesando"
        )

    # Eliminar archivo temporal si existe
    file_path = job_data.get("file_path")
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info(f"Archivo temporal eliminado: {file_path}")
        except Exception as e:
            logger.warning(f"No se pudo eliminar archivo {file_path}: {e}")

    # Eliminar trabajo de Redis
    deleted = job_queue.delete_job(job_id)

    if deleted:
        logger.info(f"Trabajo {job_id} eliminado por usuario")
        return {"message": f"Trabajo {job_id} eliminado exitosamente"}
    else:
        raise HTTPException(
            status_code=500,
            detail="Error eliminando trabajo"
        )