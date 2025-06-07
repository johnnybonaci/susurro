#!/usr/bin/env python3
"""
Script de inicio para Whisper Transcription API
"""
import uvicorn
import sys
import os
from pathlib import Path

# Agregar el directorio actual al path para imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Función principal para iniciar el servidor"""

    print("🎤 Whisper Transcription API")
    print("=" * 50)

    # Verificar dependencias críticas
    try:
        import torch
        import redis
        from faster_whisper import WhisperModel
        print("✅ Dependencias verificadas")
    except ImportError as e:
        print(f"❌ Error importando dependencias: {e}")
        print("💡 Ejecuta: pip install -r requirements.txt")
        sys.exit(1)

    # Verificar Redis
    try:
        from app.core.redis_queue import job_queue
        if job_queue.health_check():
            print("✅ Redis conectado")
        else:
            print("❌ Redis no disponible")
            print("💡 Ejecuta: sudo systemctl start redis-server")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error conectando a Redis: {e}")
        sys.exit(1)

    # Verificar GPU (opcional)
    try:
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            print(f"✅ GPU disponible: {gpu_name}")
        else:
            print("⚠️ GPU no disponible, usando CPU")
    except Exception as e:
        print(f"⚠️ Error verificando GPU: {e}")

    # Mostrar configuración
    print(f"\n📋 Configuración:")
    print(f"   - Modelo: {settings.MODEL_SIZE}")
    print(f"   - Trabajos concurrentes: {settings.MAX_CONCURRENT_JOBS}")
    print(f"   - Puerto: {settings.PORT}")
    print(f"   - Debug: {settings.DEBUG}")
    print(f"   - Log level: {settings.LOG_LEVEL}")

    print(f"\n🚀 Iniciando servidor en http://{settings.HOST}:{settings.PORT}")
    print(f"📚 Documentación: http://{settings.HOST}:{settings.PORT}/docs")
    print("=" * 50)

    # Configuración de uvicorn
    uvicorn_config = {
        "app": "app.main:app",
        "host": settings.HOST,
        "port": settings.PORT,
        "workers": settings.WORKERS,
        "log_level": settings.LOG_LEVEL.lower(),
        "access_log": True,
        "reload": settings.DEBUG,
        "loop": "uvloop" if sys.platform != "win32" else "asyncio",
    }

    # Solo usar reload en desarrollo
    if not settings.DEBUG:
        uvicorn_config.pop("reload")

    try:
        uvicorn.run(**uvicorn_config)
    except KeyboardInterrupt:
        print("\n👋 Servidor detenido por el usuario")
    except Exception as e:
        logger.error(f"Error iniciando servidor: {e}")
        print(f"❌ Error iniciando servidor: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()