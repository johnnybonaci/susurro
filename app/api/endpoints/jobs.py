from fastapi import APIRouter, Query, HTTPException
from typing import List
from app.models.schemas import QueueStats, JobSummary, JobList
from app.core.redis_queue import job_queue
from app.core.whisper_service import whisper_service
from app.utils.logger import get_logger
import torch

logger = get_logger(__name__)
router = APIRouter()


@router.get("/queue", response_model=QueueStats)
async def get_queue_statistics():
    """
    Obtener estadísticas generales de la cola de trabajos

    - Returns: Estadísticas completas de la cola y sistema
    """
    try:
        # Obtener estadísticas de Redis
        redis_stats = job_queue.get_queue_stats()

        # Obtener memoria GPU actual
        gpu_memory_mb = 0.0
        try:
            if torch.cuda.is_available():
                gpu_memory_mb = torch.cuda.memory_allocated() / (1024**2)
        except Exception as e:
            logger.warning(f"No se pudo obtener memoria GPU: {e}")

        return QueueStats(
            pending=redis_stats["pending"],
            processing=redis_stats["processing"],
            completed_today=redis_stats["completed_today"],
            failed_today=redis_stats["failed_today"],
            total_jobs=redis_stats["total_jobs"],
            average_speed=redis_stats["average_speed"],
            gpu_memory_mb=gpu_memory_mb
        )

    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de cola: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo estadísticas: {str(e)}"
        )


@router.get("/pending", response_model=List[JobSummary])
async def get_pending_jobs(
    limit: int = Query(50, ge=1, le=200, description="Número máximo de trabajos a retornar")
):
    """
    Obtener lista de trabajos pendientes en la cola

    - **limit**: Máximo número de trabajos a retornar (1-200)
    - Returns: Lista de trabajos pendientes ordenados por orden de llegada
    """
    try:
        pending_jobs = job_queue.get_pending_jobs(limit)

        job_summaries = []
        for job in pending_jobs:
            job_summaries.append(JobSummary(
                job_id=job["job_id"],
                filename=job.get("filename"),
                status=job.get("status", "pending"),
                created_at=job.get("created_at"),
                duration=None,  # No disponible para trabajos pendientes
                speed=None      # No disponible para trabajos pendientes
            ))

        logger.info(f"Retornando {len(job_summaries)} trabajos pendientes")
        return job_summaries

    except Exception as e:
        logger.error(f"Error obteniendo trabajos pendientes: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo trabajos pendientes: {str(e)}"
        )


@router.get("/recent", response_model=List[JobSummary])
async def get_recent_jobs(
    hours: int = Query(24, ge=1, le=168, description="Horas hacia atrás para buscar trabajos"),
    limit: int = Query(100, ge=1, le=500, description="Número máximo de trabajos a retornar")
):
    """
    Obtener trabajos recientes (completados y fallidos)

    - **hours**: Horas hacia atrás para buscar (1-168, default 24)
    - **limit**: Máximo número de trabajos a retornar (1-500)
    - Returns: Lista de trabajos recientes ordenados por fecha de creación
    """
    try:
        recent_jobs = job_queue.get_recent_jobs(hours, limit)

        job_summaries = []
        for job_data in recent_jobs:
            job_summaries.append(JobSummary(
                job_id=job_data["job_id"],
                filename=job_data.get("filename"),
                status=job_data.get("status"),
                created_at=job_data.get("created_at"),
                duration=job_data.get("duration"),
                speed=job_data.get("speed")
            ))

        logger.info(f"Retornando {len(job_summaries)} trabajos de las últimas {hours} horas")
        return job_summaries

    except Exception as e:
        logger.error(f"Error obteniendo trabajos recientes: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo trabajos recientes: {str(e)}"
        )


@router.get("/list", response_model=JobList)
async def list_jobs(
    status: str = Query(None, regex="^(pending|processing|completed|failed)$", description="Filtrar por estado"),
    page: int = Query(1, ge=1, description="Número de página"),
    per_page: int = Query(50, ge=1, le=200, description="Trabajos por página")
):
    """
    Listar trabajos con paginación y filtros

    - **status**: Filtrar por estado específico (opcional)
    - **page**: Número de página (default 1)
    - **per_page**: Trabajos por página (1-200, default 50)
    - Returns: Lista paginada de trabajos
    """
    try:
        # Por simplicidad, implementamos una versión básica
        # En producción podrías usar índices Redis más sofisticados

        if status == "pending":
            jobs = job_queue.get_pending_jobs(per_page * page)
        else:
            # Para otros estados, usar trabajos recientes como aproximación
            jobs = job_queue.get_recent_jobs(hours=24*7, limit=per_page * page)
            if status:
                jobs = [job for job in jobs if job.get("status") == status]

        # Paginación simple
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_jobs = jobs[start_idx:end_idx]

        job_summaries = []
        for job_data in page_jobs:
            if isinstance(job_data, dict) and "job_id" in job_data:
                job_summaries.append(JobSummary(
                    job_id=job_data["job_id"],
                    filename=job_data.get("filename"),
                    status=job_data.get("status"),
                    created_at=job_data.get("created_at"),
                    duration=job_data.get("duration"),
                    speed=job_data.get("speed")
                ))

        return JobList(
            jobs=job_summaries,
            total=len(jobs),
            page=page,
            per_page=per_page
        )

    except Exception as e:
        logger.error(f"Error listando trabajos: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listando trabajos: {str(e)}"
        )


@router.get("/search/{query}")
async def search_jobs(
    query: str,
    limit: int = Query(50, ge=1, le=200, description="Número máximo de resultados")
):
    """
    Buscar trabajos por nombre de archivo

    - **query**: Término de búsqueda para nombre de archivo
    - **limit**: Máximo número de resultados
    - Returns: Lista de trabajos que coinciden con la búsqueda
    """
    try:
        # Obtener trabajos recientes para buscar
        recent_jobs = job_queue.get_recent_jobs(hours=24*7, limit=500)

        # Filtrar por query en filename
        matching_jobs = []
        for job_data in recent_jobs:
            filename = job_data.get("filename", "")
            if query.lower() in filename.lower():
                matching_jobs.append(JobSummary(
                    job_id=job_data["job_id"],
                    filename=job_data.get("filename"),
                    status=job_data.get("status"),
                    created_at=job_data.get("created_at"),
                    duration=job_data.get("duration"),
                    speed=job_data.get("speed")
                ))

                if len(matching_jobs) >= limit:
                    break

        logger.info(f"Búsqueda '{query}' retornó {len(matching_jobs)} resultados")
        return matching_jobs

    except Exception as e:
        logger.error(f"Error en búsqueda: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error en búsqueda: {str(e)}"
        )


@router.get("/stats/performance")
async def get_performance_stats():
    """
    Obtener estadísticas detalladas de rendimiento

    - Returns: Métricas de rendimiento del sistema
    """
    try:
        # Estadísticas de cola
        queue_stats = job_queue.get_queue_stats()

        # Información GPU
        gpu_info = whisper_service.get_gpu_info()

        # Modelos disponibles
        available_models = whisper_service.get_available_models_count()

        # Información Redis
        redis_info = job_queue.get_connection_info()

        return {
            "queue_statistics": queue_stats,
            "gpu_information": gpu_info,
            "model_pool": {
                "available_models": available_models,
                "max_concurrent": settings.MAX_CONCURRENT_JOBS,
                "utilization_percent": ((settings.MAX_CONCURRENT_JOBS - available_models) / settings.MAX_CONCURRENT_JOBS) * 100
            },
            "redis_information": redis_info,
            "configuration": {
                "model_size": settings.MODEL_SIZE,
                "max_file_size_mb": settings.MAX_FILE_SIZE / (1024 * 1024),
                "allowed_formats": settings.ALLOWED_EXTENSIONS
            }
        }

    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de rendimiento: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo estadísticas: {str(e)}"
        )