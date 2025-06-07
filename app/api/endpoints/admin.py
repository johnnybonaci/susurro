from fastapi import APIRouter, Query, HTTPException
from app.models.schemas import HealthCheck, APIInfo, CleanupResponse, AdminStats
from app.core.redis_queue import job_queue
from app.core.whisper_service import whisper_service
from app.config import settings
from app.utils.logger import get_logger
import time
import os
import psutil

logger = get_logger(__name__)
router = APIRouter()

# Tiempo de inicio para calcular uptime
start_time = time.time()


@router.get("/health", response_model=HealthCheck)
async def health_check():
    """
    Verificar estado de salud del sistema

    - Returns: Estado de todos los componentes del sistema
    """
    try:
        # Verificar Redis
        redis_connected = job_queue.health_check()

        # Verificar GPU
        gpu_info = whisper_service.get_gpu_info()
        gpu_available = gpu_info.get("available", False)
        gpu_memory_mb = gpu_info.get("memory_allocated_mb", 0.0)

        # Verificar modelos disponibles
        models_available = whisper_service.get_available_models_count()

        # Calcular uptime
        uptime_seconds = time.time() - start_time

        # Determinar estado general
        status = "healthy"
        if not redis_connected:
            status = "unhealthy"
        elif not gpu_available or models_available == 0:
            status = "degraded"

        return HealthCheck(
            status=status,
            redis_connected=redis_connected,
            models_available=models_available,
            gpu_available=gpu_available,
            gpu_memory_mb=gpu_memory_mb,
            uptime_seconds=uptime_seconds
        )

    except Exception as e:
        logger.error(f"Error en health check: {e}")
        return HealthCheck(
            status="error",
            redis_connected=False,
            models_available=0,
            gpu_available=False,
            gpu_memory_mb=0.0,
            uptime_seconds=time.time() - start_time
        )


@router.get("/info", response_model=APIInfo)
async def get_api_info():
    """
    Información general de la API

    - Returns: Configuración y capacidades de la API
    """
    return APIInfo(
        title=settings.API_TITLE,
        version=settings.API_VERSION,
        model_size=settings.MODEL_SIZE,
        max_concurrent_jobs=settings.MAX_CONCURRENT_JOBS,
        allowed_formats=settings.ALLOWED_EXTENSIONS,
        max_file_size_mb=settings.MAX_FILE_SIZE // (1024 * 1024)
    )


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup_old_jobs(
    days: int = Query(7, ge=1, le=30, description="Días de antigüedad para limpiar trabajos")
):
    """
    Limpiar trabajos y archivos antiguos

    - **days**: Días de antigüedad (1-30, default 7)
    - Returns: Número de trabajos y archivos limpiados
    """
    try:
        logger.info(f"Iniciando limpieza de trabajos antiguos (>{days} días)")

        # Limpiar trabajos de Redis
        jobs_cleaned = job_queue.cleanup_old_jobs(days)

        # Limpiar archivos temporales antiguos
        files_cleaned = 0
        cutoff_time = time.time() - (days * 24 * 3600)

        if os.path.exists(settings.UPLOAD_DIR):
            for filename in os.listdir(settings.UPLOAD_DIR):
                file_path = os.path.join(settings.UPLOAD_DIR, filename)
                try:
                    if os.path.isfile(file_path):
                        file_mtime = os.path.getmtime(file_path)
                        if file_mtime < cutoff_time:
                            os.remove(file_path)
                            files_cleaned += 1
                except Exception as e:
                    logger.warning(f"No se pudo eliminar archivo {file_path}: {e}")

        logger.info(f"Limpieza completada: {jobs_cleaned} trabajos, {files_cleaned} archivos")

        return CleanupResponse(
            message=f"Limpieza completada exitosamente",
            jobs_cleaned=jobs_cleaned,
            files_cleaned=files_cleaned
        )

    except Exception as e:
        logger.error(f"Error durante limpieza: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error durante limpieza: {str(e)}"
        )


@router.post("/reset-daily-stats")
async def reset_daily_statistics():
    """
    Resetear estadísticas diarias

    - Returns: Confirmación de reset
    """
    try:
        job_queue.reset_daily_stats()
        logger.info("Estadísticas diarias reseteadas manualmente")

        return {"message": "Estadísticas diarias reseteadas exitosamente"}

    except Exception as e:
        logger.error(f"Error reseteando estadísticas: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error reseteando estadísticas: {str(e)}"
        )


@router.post("/clear-gpu-memory")
async def clear_gpu_memory():
    """
    Limpiar memoria GPU manualmente

    - Returns: Estado de la memoria después de limpiar
    """
    try:
        # Memoria antes de limpiar
        gpu_info_before = whisper_service.get_gpu_info()
        memory_before = gpu_info_before.get("memory_allocated_mb", 0)

        # Limpiar memoria
        whisper_service.cleanup_memory()

        # Memoria después de limpiar
        gpu_info_after = whisper_service.get_gpu_info()
        memory_after = gpu_info_after.get("memory_allocated_mb", 0)

        memory_freed = memory_before - memory_after

        logger.info(f"Memoria GPU limpiada: {memory_freed:.1f}MB liberados")

        return {
            "message": "Memoria GPU limpiada",
            "memory_before_mb": memory_before,
            "memory_after_mb": memory_after,
            "memory_freed_mb": memory_freed
        }

    except Exception as e:
        logger.error(f"Error limpiando memoria GPU: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error limpiando memoria GPU: {str(e)}"
        )


@router.get("/stats", response_model=AdminStats)
async def get_admin_statistics():
    """
    Estadísticas administrativas completas

    - Returns: Estadísticas detalladas del sistema
    """
    try:
        # Estadísticas de cola
        queue_stats = job_queue.get_queue_stats()

        # Trabajos recientes
        recent_jobs = job_queue.get_recent_jobs(hours=24, limit=20)

        # Información del sistema
        try:
            system_info = {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage_percent": psutil.disk_usage("/").percent if os.path.exists("/") else 0,
                "uptime_seconds": time.time() - start_time
            }
        except Exception:
            system_info = {
                "cpu_percent": 0,
                "memory_percent": 0,
                "disk_usage_percent": 0,
                "uptime_seconds": time.time() - start_time
            }

        # Métricas de rendimiento
        gpu_info = whisper_service.get_gpu_info()
        performance_metrics = {
            "models_available": whisper_service.get_available_models_count(),
            "max_models": settings.MAX_CONCURRENT_JOBS,
            "gpu_info": gpu_info,
            "redis_info": job_queue.get_connection_info()
        }

        # Convertir recent_jobs al formato JobSummary
        from app.models.schemas import JobSummary
        job_summaries = []
        for job_data in recent_jobs[:10]:  # Limitar a 10 para el admin
            job_summaries.append(JobSummary(
                job_id=job_data["job_id"],
                filename=job_data.get("filename"),
                status=job_data.get("status"),
                created_at=job_data.get("created_at"),
                duration=job_data.get("duration"),
                speed=job_data.get("speed")
            ))

        return AdminStats(
            system_info=system_info,
            queue_stats=queue_stats,
            recent_jobs=job_summaries,
            performance_metrics=performance_metrics
        )

    except Exception as e:
        logger.error(f"Error obteniendo estadísticas administrativas: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo estadísticas: {str(e)}"
        )


@router.get("/logs")
async def get_recent_logs(
    lines: int = Query(100, ge=10, le=1000, description="Número de líneas de log")
):
    """
    Obtener logs recientes del sistema

    - **lines**: Número de líneas a retornar (10-1000)
    - Returns: Últimas líneas del log
    """
    try:
        log_lines = []

        if os.path.exists(settings.LOG_FILE):
            with open(settings.LOG_FILE, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                log_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

        return {
            "total_lines": len(log_lines),
            "logs": [line.strip() for line in log_lines]
        }

    except Exception as e:
        logger.error(f"Error obteniendo logs: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo logs: {str(e)}"
        )


@router.get("/config")
async def get_current_config():
    """
    Obtener configuración actual del sistema

    - Returns: Configuración actual (sin datos sensibles)
    """
    return {
        "whisper": {
            "model_size": settings.MODEL_SIZE,
            "max_concurrent_jobs": settings.MAX_CONCURRENT_JOBS,
            "device": settings.DEVICE,
            "compute_type": settings.COMPUTE_TYPE
        },
        "files": {
            "max_file_size_mb": settings.MAX_FILE_SIZE // (1024 * 1024),
            "allowed_extensions": settings.ALLOWED_EXTENSIONS,
            "upload_dir": settings.UPLOAD_DIR
        },
        "optimization": {
            "beam_size": settings.BEAM_SIZE,
            "vad_filter": settings.VAD_FILTER,
            "chunk_length": settings.CHUNK_LENGTH
        },
        "redis": {
            "host": settings.REDIS_HOST,
            "port": settings.REDIS_PORT,
            "db": settings.REDIS_DB
        }
    }