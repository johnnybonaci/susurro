from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time

from app.config import settings
from app.api.endpoints import transcription, jobs, admin
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Tiempo de inicio para uptime
app_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestión del ciclo de vida de la aplicación
    """
    # Startup
    logger.info("🚀 Iniciando Whisper Transcription API")
    logger.info(f"📋 Configuración:")
    logger.info(f"   - Modelo: {settings.MODEL_SIZE}")
    logger.info(f"   - Trabajos concurrentes: {settings.MAX_CONCURRENT_JOBS}")
    logger.info(f"   - Dispositivo: {settings.DEVICE}")
    logger.info(f"   - Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")

    # Verificar conexiones iniciales
    try:
        from app.core.redis_queue import job_queue
        from app.core.whisper_service import whisper_service

        # Test Redis
        if job_queue.health_check():
            logger.info("✅ Redis conectado")
        else:
            logger.warning("⚠️ Redis no disponible")

        # Test GPU
        gpu_info = whisper_service.get_gpu_info()
        if gpu_info.get("available"):
            logger.info(f"✅ GPU disponible: {gpu_info.get('device_name')}")
        else:
            logger.warning("⚠️ GPU no disponible, usando CPU")

        # Test modelo
        models_count = whisper_service.get_available_models_count()
        logger.info(f"✅ {models_count}/{settings.MAX_CONCURRENT_JOBS} modelos cargados")

    except Exception as e:
        logger.error(f"❌ Error durante inicialización: {e}")

    logger.info("🎯 API lista para recibir requests")

    yield

    # Shutdown
    logger.info("🛑 Cerrando Whisper Transcription API")
    logger.info("🧹 Limpiando recursos...")

    try:
        from app.core.whisper_service import whisper_service
        whisper_service.cleanup_memory()
        logger.info("✅ Memoria GPU limpiada")
    except Exception as e:
        logger.warning(f"⚠️ Error limpiando memoria: {e}")

    logger.info("👋 API cerrada exitosamente")


# Crear aplicación FastAPI
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar dominios exactos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Middleware para logging de requests
@app.middleware("http")
async def log_requests(request, call_next):
    """Middleware para loggear requests"""
    start_time = time.time()

    # Procesar request
    response = await call_next(request)

    # Calcular tiempo de procesamiento
    process_time = time.time() - start_time

    # Log del request
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.3f}s"
    )

    # Agregar header con tiempo de procesamiento
    response.headers["X-Process-Time"] = str(process_time)

    return response


# Manejador global de excepciones
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Manejador global de excepciones no capturadas"""
    logger.error(f"Error no manejado en {request.method} {request.url}: {exc}")

    return JSONResponse(
        status_code=500,
        content={
            "error": "Error interno del servidor",
            "details": "Se ha producido un error inesperado. Por favor, inténtelo más tarde.",
            "request_id": str(int(time.time() * 1000))  # Simple request ID
        }
    )


# Manejador para HTTPException
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Manejador para excepciones HTTP"""
    logger.warning(f"HTTP {exc.status_code} en {request.method} {request.url}: {exc.detail}")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )


# Incluir routers de endpoints
app.include_router(
    transcription.router,
    prefix="/api/v1",
    tags=["Transcripción"],
    responses={
        400: {"description": "Error en la solicitud"},
        404: {"description": "Recurso no encontrado"},
        500: {"description": "Error interno del servidor"}
    }
)

app.include_router(
    jobs.router,
    prefix="/api/v1/jobs",
    tags=["Trabajos"],
    responses={
        500: {"description": "Error interno del servidor"}
    }
)

app.include_router(
    admin.router,
    prefix="/api/v1/admin",
    tags=["Administración"],
    responses={
        500: {"description": "Error interno del servidor"}
    }
)


# Endpoints raíz
@app.get("/")
async def root():
    """
    Endpoint raíz con información básica de la API
    """
    try:
        from app.core.redis_queue import job_queue
        from app.core.whisper_service import whisper_service

        # Obtener estadísticas básicas
        queue_stats = job_queue.get_queue_stats()
        models_available = whisper_service.get_available_models_count()
        uptime = time.time() - app_start_time

        return {
            "message": "🎤 Whisper Transcription API",
            "version": settings.API_VERSION,
            "status": "operational",
            "uptime_seconds": uptime,
            "configuration": {
                "model": settings.MODEL_SIZE,
                "max_concurrent_jobs": settings.MAX_CONCURRENT_JOBS,
                "max_file_size_mb": settings.MAX_FILE_SIZE // (1024 * 1024),
                "supported_formats": settings.ALLOWED_EXTENSIONS
            },
            "current_stats": {
                "models_available": models_available,
                "pending_jobs": queue_stats.get("pending", 0),
                "processing_jobs": queue_stats.get("processing", 0),
                "completed_today": queue_stats.get("completed_today", 0)
            },
            "endpoints": {
                "transcribe": "/api/v1/transcribe",
                "health": "/api/v1/admin/health",
                "queue_stats": "/api/v1/jobs/queue",
                "documentation": "/docs"
            }
        }

    except Exception as e:
        logger.error(f"Error en endpoint raíz: {e}")
        return {
            "message": "🎤 Whisper Transcription API",
            "version": settings.API_VERSION,
            "status": "degraded",
            "error": "Error obteniendo estadísticas"
        }


@app.get("/favicon.ico")
async def favicon():
    """Evitar logs de error por favicon"""
    return JSONResponse(status_code=204, content=None)


# Endpoint de versión
@app.get("/version")
async def get_version():
    """Información de versión"""
    return {
        "version": settings.API_VERSION,
        "api_title": settings.API_TITLE,
        "model_size": settings.MODEL_SIZE
    }


# Endpoint de métricas básicas (para monitoreo)
@app.get("/metrics")
async def get_metrics():
    """
    Métricas básicas en formato simple para monitoreo externo
    """
    try:
        from app.core.redis_queue import job_queue
        from app.core.whisper_service import whisper_service
        import torch

        queue_stats = job_queue.get_queue_stats()
        gpu_memory = 0

        if torch.cuda.is_available():
            gpu_memory = torch.cuda.memory_allocated() / (1024**2)

        return {
            "whisper_pending_jobs": queue_stats.get("pending", 0),
            "whisper_processing_jobs": queue_stats.get("processing", 0),
            "whisper_completed_today": queue_stats.get("completed_today", 0),
            "whisper_failed_today": queue_stats.get("failed_today", 0),
            "whisper_models_available": whisper_service.get_available_models_count(),
            "whisper_gpu_memory_mb": gpu_memory,
            "whisper_uptime_seconds": time.time() - app_start_time,
            "whisper_average_speed": queue_stats.get("average_speed", 0)
        }

    except Exception as e:
        logger.error(f"Error obteniendo métricas: {e}")
        return {"error": "Error obteniendo métricas"}


if __name__ == "__main__":
    import uvicorn

    logger.info("🚀 Iniciando servidor directamente...")

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
        reload=settings.DEBUG
    )