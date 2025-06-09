import time
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.gzip import GZipMiddleware

from app.config import settings
from app.api.endpoints.transcription import router as transcription_router, processing_state
from app.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión de ciclo de vida ultra-optimizada"""

    # === STARTUP ===
    logger.info("🚀 Iniciando Whisper API Always-On")

    try:
        from app.core.whisper_service import whisper_service

        # El modelo se carga automáticamente en whisper_service
        logger.info("✅ Whisper service (always-loaded mode)")

    except Exception as e:
        logger.error(f"❌ Error startup: {e}")

    logger.info("🎯 API always-on lista - Modelo pre-cargado")

    yield

    # === SHUTDOWN ===
    logger.info("🛑 Cerrando API...")

    try:
        from app.core.whisper_service import whisper_service
        # En always-on mode, force_unload no hace nada
        await whisper_service.force_unload()
        logger.info("✅ Shutdown completado")
    except Exception as e:
        logger.warning(f"⚠️ Error en shutdown: {e}")


# === APLICACIÓN ALWAYS-ON ===
app = FastAPI(
    title="Whisper API Always-On Ultra-Optimizada",
    description="Transcripción directa con modelo siempre cargado - Máxima velocidad",
    version="3.0.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None
)

# === MIDDLEWARE ESENCIAL ===
if settings.RESPONSE_COMPRESSION:
    app.add_middleware(GZipMiddleware, minimum_size=1000)

# Middleware ultra-rápido
@app.middleware("http")
async def ultra_fast_middleware(request: Request, call_next):
    """Middleware optimizado - solo timing"""
    start_time = time.time()
    response = await call_next(request)

    process_time = (time.time() - start_time) * 1000
    response.headers["X-Process-Time"] = f"{process_time:.1f}ms"

    return response

# === MANEJADORES DE ERRORES ===
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Manejador global ultra-simple"""
    logger.error(f"❌ Error: {request.method} {request.url.path} - {exc}")

    return JSONResponse(
        status_code=500,
        content={
            "error": "Error interno del servidor",
            "timestamp": int(time.time()),
            "path": str(request.url.path)
        }
    )

# === ROUTER PRINCIPAL ===
app.include_router(
    transcription_router,
    prefix="/api/v1",
    tags=["Transcripción Always-On"]
)

# === ENDPOINTS RAÍZ ===
@app.get("/")
async def root():
    """Endpoint raíz con información de la API always-on"""
    try:
        from app.core.whisper_service import whisper_service

        service_status = await whisper_service.get_status()

        return {
            "service": "Whisper API Always-On Ultra-Optimizada",
            "version": "3.0.0",
            "mode": "always_loaded",
            "description": "Modelo siempre cargado → Máxima velocidad constante",
            "status": "processing" if processing_state["is_processing"] else "ready",
            "current_load": {
                "is_processing": processing_state["is_processing"],
                "can_accept": not processing_state["is_processing"] and service_status["can_accept_jobs"],
                "current_job": processing_state.get("current_job"),
                "model_uptime_hours": service_status.get("uptime_hours", 0)
            },
            "config": {
                "model": settings.MODEL_SIZE,
                "max_file_mb": settings.MAX_FILE_SIZE // (1024 * 1024),
                "supported_formats": settings.ALLOWED_EXTENSIONS,
                "always_loaded": True,
                "lazy_loading": False
            },
            "performance": {
                "model_preloaded": service_status.get("model_loaded", False),
                "total_transcriptions": service_status.get("total_transcriptions", 0),
                "estimated_response_time": "~70 segundos constante",
                "no_loading_delays": True
            },
            "endpoints": {
                "transcribe": "POST /api/v1/transcribe (modelo pre-cargado)",
                "status": "GET /api/v1/status",
                "health": "GET /api/v1/health",
                "cancel": "POST /api/v1/cancel",
                "docs": "/docs"
            },
            "usage": {
                "simple": "curl -F 'file=@audio.mp3' http://localhost:8000/api/v1/transcribe",
                "check_status": "curl http://localhost:8000/api/v1/status",
                "if_busy": "Recibirás HTTP 202 con 'retry_after' si está procesando"
            },
            "hardware": {
                "device": settings.DEVICE,
                "compute_type": settings.COMPUTE_TYPE,
                "memory_mb": round(service_status["memory_info"].get("ram_usage_mb", 0), 1),
                "gpu_memory_mb": round(service_status["memory_info"].get("gpu_memory_allocated_mb", 0), 1)
            }
        }

    except Exception as e:
        logger.error(f"❌ Error endpoint raíz: {e}")
        return {
            "service": "Whisper API Always-On",
            "status": "degraded",
            "error": "Error obteniendo estado completo",
            "mode": "always_loaded",
            "note": "El modelo debería estar cargándose en background"
        }

@app.get("/metrics")
async def minimal_metrics():
    """Métricas básicas para monitoreo"""
    try:
        from app.core.whisper_service import whisper_service

        service_status = await whisper_service.get_status()

        return {
            "whisper_processing": 1 if processing_state["is_processing"] else 0,
            "whisper_available": 1 if service_status["can_accept_jobs"] and not processing_state["is_processing"] else 0,
            "whisper_model_loaded": 1 if service_status["model_loaded"] else 0,
            "whisper_model_always_loaded": 1 if service_status.get("model_always_loaded", False) else 0,
            "whisper_uptime_hours": service_status.get("uptime_hours", 0),
            "whisper_total_transcriptions": service_status.get("total_transcriptions", 0),
            "whisper_memory_mb": service_status["memory_info"].get("ram_usage_mb", 0),
            "whisper_gpu_memory_mb": service_status["memory_info"].get("gpu_memory_allocated_mb", 0)
        }

    except Exception as e:
        logger.error(f"❌ Error métricas: {e}")
        return {"error": "métricas no disponibles"}

@app.get("/favicon.ico")
async def favicon():
    """Evitar logs 404 de favicon"""
    return JSONResponse(status_code=204, content=None)

# === STARTUP DIRECTO ===
if __name__ == "__main__":
    import uvicorn

    logger.info("🚀 Iniciando servidor always-on directo...")

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        workers=1,
        log_level="warning",
        access_log=False,
        reload=False
    )