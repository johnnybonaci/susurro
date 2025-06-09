import os
import uuid
import asyncio
import aiofiles
import time
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional

from app.config import settings
from app.core.whisper_service import whisper_service
from app.core.redis_semaphore import processing_semaphore
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class ValidationError(Exception):
    """Error de validación rápida"""
    pass


async def ultra_fast_validation(file: UploadFile) -> Dict[str, Any]:
    """Validación ultra-rápida sin operaciones costosas"""

    if not file.filename:
        raise ValidationError("Nombre de archivo requerido")

    # Validar extensión
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"Formato no soportado: {file_ext}. "
            f"Permitidos: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )

    # Validar tamaño si está disponible
    if hasattr(file, 'size') and file.size:
        if file.size > settings.MAX_FILE_SIZE:
            size_mb = file.size / (1024 * 1024)
            max_mb = settings.MAX_FILE_SIZE / (1024 * 1024)
            raise ValidationError(
                f"Archivo muy grande: {size_mb:.1f}MB. Máximo: {max_mb}MB"
            )

    return {
        "filename": file.filename,
        "extension": file_ext,
        "size": getattr(file, 'size', None)
    }


async def stream_file_to_disk(file: UploadFile, filepath: str) -> int:
    """Guardar archivo usando streaming para memoria mínima"""
    total_size = 0
    chunk_size = 8192  # 8KB chunks

    try:
        async with aiofiles.open(filepath, 'wb') as f:
            while chunk := await file.read(chunk_size):
                total_size += len(chunk)
                if total_size > settings.MAX_FILE_SIZE:
                    await f.close()
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    raise ValidationError(
                        f"Archivo excede tamaño máximo: {total_size / (1024 * 1024):.1f}MB"
                    )
                await f.write(chunk)

        return total_size

    except Exception as e:
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass
        raise


@router.post("/transcribe")
async def transcribe_audio_sync(file: UploadFile = File(...)) -> JSONResponse:
    """
    Endpoint de transcripción síncrona con control Redis robusto

    - Verifica estado con Redis antes de procesar
    - Solo permite un proceso a la vez
    - Responde inmediatamente si está ocupado
    """
    start_time = time.time()

    # === VERIFICAR ESTADO CON REDIS (< 5ms) ===
    if await processing_semaphore.is_processing():
        # Sistema ocupado, obtener detalles del proceso actual
        current_status = await processing_semaphore.get_current_status()

        if current_status:
            return JSONResponse(
                status_code=202,  # Accepted - Processing
                content={
                    "status": "processing",
                    "message": "Sistema procesando otro audio",
                    "current_job": current_status.get("job_id"),
                    "current_filename": current_status.get("filename"),
                    "elapsed_seconds": current_status.get("elapsed_seconds", 0),
                    "estimated_remaining_seconds": current_status.get("estimated_remaining_seconds", 30),
                    "retry_after": 10,
                    "response_time_ms": round((time.time() - start_time) * 1000, 1)
                },
                headers={
                    "Retry-After": "10",
                    "X-Processing-Status": "busy",
                    "X-Current-Job": current_status.get("job_id", "unknown")
                }
            )

    # === VALIDACIONES RÁPIDAS ===
    try:
        file_info = await ultra_fast_validation(file)
    except ValidationError as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Error de validación",
                "details": str(e),
                "response_time_ms": round((time.time() - start_time) * 1000, 1)
            }
        )

    # === VERIFICAR SERVICIO WHISPER ===
    if not await whisper_service.can_process_job():
        return JSONResponse(
            status_code=503,
            content={
                "error": "Servicio Whisper no disponible",
                "message": "Modelo no cargado o sistema ocupado",
                "retry_after": 15,
                "response_time_ms": round((time.time() - start_time) * 1000, 1)
            },
            headers={"Retry-After": "15"}
        )

    # === INTENTAR ADQUIRIR LOCK ===
    job_id = str(uuid.uuid4())[:8]
    temp_filename = f"{job_id}{file_info['extension']}"
    temp_path = os.path.join(settings.UPLOAD_DIR, temp_filename)

    # Streaming del archivo primero (para obtener tamaño real)
    try:
        file_size = await stream_file_to_disk(file, temp_path)
    except ValidationError as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Error procesando archivo",
                "details": str(e),
                "response_time_ms": round((time.time() - start_time) * 1000, 1)
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Error interno guardando archivo",
                "details": str(e),
                "response_time_ms": round((time.time() - start_time) * 1000, 1)
            }
        )

    # Preparar info del job
    job_info = {
        "filename": file_info["filename"],
        "file_size": file_size,
        "extension": file_info["extension"]
    }

    # Intentar adquirir lock
    lock_acquired = await processing_semaphore.acquire_lock(job_id, job_info)

    if not lock_acquired:
        # No se pudo adquirir lock, limpiar archivo y retornar ocupado
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except:
            pass

        # Obtener estado actual
        current_status = await processing_semaphore.get_current_status()

        return JSONResponse(
            status_code=202,
            content={
                "status": "processing",
                "message": "Sistema ocupado, otro proceso en curso",
                "current_job": current_status.get("job_id", "unknown") if current_status else "unknown",
                "retry_after": 10,
                "note": "Tu archivo fue validado correctamente, reintenta en unos segundos",
                "response_time_ms": round((time.time() - start_time) * 1000, 1)
            },
            headers={"Retry-After": "10"}
        )

    # === PROCESAMIENTO CON LOCK ADQUIRIDO ===
    try:
        logger.info(f"🎤 Iniciando transcripción {job_id}: {file_info['filename']} ({file_size} bytes)")

        # Transcripción directa
        result = await whisper_service.transcribe_audio(temp_path)

        # Agregar metadatos
        result.update({
            "job_id": job_id,
            "filename": file_info["filename"],
            "file_size": file_size,
            "status": "completed",
            "total_time": time.time() - start_time,
            "response_time_ms": round((time.time() - start_time) * 1000, 1)
        })

        logger.info(f"✅ Transcripción {job_id} completada en {result['total_time']:.2f}s (velocidad: {result.get('speed', 0):.1f}x)")

        return JSONResponse(
            status_code=200,
            content=result,
            headers={
                "X-Job-ID": job_id,
                "X-Processing-Time": f"{result['total_time']:.2f}s",
                "X-Speed": f"{result.get('speed', 0):.1f}x",
                "X-File-Size": str(file_size)
            }
        )

    except Exception as e:
        logger.error(f"❌ Error transcripción {job_id}: {e}")

        return JSONResponse(
            status_code=500,
            content={
                "error": "Error durante transcripción",
                "details": str(e),
                "job_id": job_id,
                "response_time_ms": round((time.time() - start_time) * 1000, 1)
            }
        )

    finally:
        # === LIMPIEZA GARANTIZADA ===

        # 1. Liberar lock Redis
        try:
            await processing_semaphore.release_lock(job_id)
        except Exception as e:
            logger.error(f"❌ Error liberando lock {job_id}: {e}")

        # 2. Limpiar archivo temporal
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                logger.debug(f"🗑️ Archivo temporal eliminado: {temp_path}")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo eliminar {temp_path}: {e}")


@router.get("/status")
async def get_processing_status() -> JSONResponse:
    """
    Estado actual del sistema con información Redis
    """
    start_time = time.time()

    try:
        # Estado del procesamiento desde Redis
        current_status = await processing_semaphore.get_current_status()
        is_processing = await processing_semaphore.is_processing()

        # Estado del servicio Whisper
        service_status = await whisper_service.get_status()

        # Construir respuesta
        response_data = {
            "system_status": "processing" if is_processing else "available",
            "is_processing": is_processing,
            "can_accept_new": not is_processing and service_status["can_accept_jobs"],
            "redis_connected": await processing_semaphore.health_check()
        }

        # Agregar detalles del proceso actual si existe
        if current_status:
            response_data.update({
                "current_process": {
                    "job_id": current_status.get("job_id"),
                    "filename": current_status.get("filename"),
                    "elapsed_seconds": current_status.get("elapsed_seconds"),
                    "estimated_remaining": current_status.get("estimated_remaining_seconds"),
                    "file_size_mb": round(current_status.get("file_size", 0) / (1024 * 1024), 2)
                }
            })

        # Información del servicio
        response_data.update({
            "service_info": {
                "model_loaded": service_status["model_loaded"],
                "memory_usage_mb": round(service_status["memory_info"].get("ram_usage_mb", 0), 1),
                "gpu_memory_mb": round(service_status["memory_info"].get("gpu_memory_allocated_mb", 0), 1)
            },
            "configuration": {
                "model_size": settings.MODEL_SIZE,
                "max_file_size_mb": settings.MAX_FILE_SIZE // (1024 * 1024),
                "supported_formats": settings.ALLOWED_EXTENSIONS,
                "lazy_loading": settings.LAZY_MODEL_LOADING
            },
            "response_time_ms": round((time.time() - start_time) * 1000, 1)
        })

        return JSONResponse(content=response_data)

    except Exception as e:
        logger.error(f"❌ Error obteniendo status: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Error obteniendo estado del sistema",
                "details": str(e)
            }
        )


@router.post("/cancel")
async def cancel_processing() -> JSONResponse:
    """
    Cancelar procesamiento actual (liberación forzada del lock)
    """
    try:
        current_status = await processing_semaphore.get_current_status()

        if not current_status:
            return JSONResponse(
                status_code=200,
                content={
                    "message": "No hay procesamiento en curso",
                    "status": "idle"
                }
            )

        # Forzar liberación del lock
        released = await processing_semaphore.force_release()

        if released:
            job_id = current_status.get("job_id", "unknown")
            logger.info(f"🛑 Procesamiento {job_id} cancelado forzadamente")

            return JSONResponse(content={
                "message": f"Procesamiento {job_id} cancelado",
                "previous_job": job_id,
                "note": "Lock liberado, sistema disponible para nuevos requests",
                "status": "cancelled"
            })
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "No se pudo cancelar el procesamiento",
                    "note": "Reintentar o esperar a que termine naturalmente"
                }
            )

    except Exception as e:
        logger.error(f"❌ Error cancelando: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Error durante cancelación",
                "details": str(e)
            }
        )


@router.get("/health")
async def health_check() -> JSONResponse:
    """Health check con verificación Redis"""
    try:
        # Verificar componentes
        redis_ok = await processing_semaphore.health_check()
        service_status = await whisper_service.get_status()
        is_processing = await processing_semaphore.is_processing()

        # Determinar estado general
        if not redis_ok:
            status = "unhealthy"
        elif is_processing:
            status = "processing"
        elif not service_status["can_accept_jobs"]:
            status = "degraded"
        else:
            status = "healthy"

        return JSONResponse(content={
            "status": status,
            "components": {
                "redis": redis_ok,
                "whisper_service": service_status["can_accept_jobs"],
                "model_loaded": service_status["model_loaded"]
            },
            "processing": {
                "is_processing": is_processing,
                "can_accept_requests": not is_processing and redis_ok
            },
            "memory": {
                "ram_mb": round(service_status["memory_info"].get("ram_usage_mb", 0), 1),
                "gpu_mb": round(service_status["memory_info"].get("gpu_memory_allocated_mb", 0), 1)
            }
        })

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )