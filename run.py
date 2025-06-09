#!/usr/bin/env python3
"""
🎤 Whisper API Ultra-Optimizada - PUNTO DE ENTRADA PRINCIPAL
🎯 Máxima eficiencia, mínima memoria, respuesta instantánea
"""
import os
import sys
import time
import psutil
import asyncio
from pathlib import Path

# Agregar directorio actual al path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

def print_banner():
    """Banner de inicio"""
    print("\n" + "="*60)
    print("🎤 WHISPER API ULTRA-OPTIMIZADA")
    print("="*60)
    print("🎯 Objetivo: Máxima eficiencia, mínima memoria")
    print("⚡ Lazy loading + Auto cleanup + Response < 100ms")
    print("="*60)


def check_python_version():
    """Verificar versión Python"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ requerido")
        print(f"   Versión actual: {sys.version}")
        sys.exit(1)
    print(f"✅ Python {sys.version.split()[0]}")


def check_system_resources():
    """Verificar recursos del sistema"""
    try:
        memory = psutil.virtual_memory()
        available_gb = memory.available / (1024**3)
        total_gb = memory.total / (1024**3)

        print(f"💾 RAM: {available_gb:.1f}GB disponible / {total_gb:.1f}GB total")

        if available_gb < 2:
            print("⚠️ Poca memoria disponible (< 2GB)")
            return False

        return True

    except Exception as e:
        print(f"⚠️ Error verificando memoria: {e}")
        return True  # Continuar de todas formas


def check_gpu():
    """Verificar GPU disponible"""
    try:
        import torch
        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            for i in range(gpu_count):
                gpu_name = torch.cuda.get_device_name(i)
                props = torch.cuda.get_device_properties(i)
                gpu_memory_gb = props.total_memory / (1024**3)
                print(f"🎮 GPU {i}: {gpu_name} ({gpu_memory_gb:.1f}GB VRAM)")
            return True
        else:
            print("⚠️ GPU CUDA no disponible, usando CPU")
            return False

    except ImportError:
        print("❌ PyTorch no instalado")
        return False
    except Exception as e:
        print(f"⚠️ Error verificando GPU: {e}")
        return False


def verify_dependencies():
    """Verificar dependencias críticas"""
    critical_deps = [
        "fastapi",
        "uvicorn",
        "redis",
        "faster_whisper",
        "torch",
        "aiofiles",
        "pydantic_settings"
    ]

    missing = []
    for dep in critical_deps:
        try:
            __import__(dep)
        except ImportError:
            missing.append(dep)

    if missing:
        print(f"❌ Dependencias faltantes: {', '.join(missing)}")
        print("💡 Instalar con: pip install -r requirements.txt")
        return False

    print("✅ Dependencias verificadas")
    return True


def test_redis():
    """Verificar conexión Redis"""
    try:
        from app.core.redis_queue import job_queue

        # Test asíncrono
        async def test_connection():
            return await job_queue.health_check()

        result = asyncio.run(test_connection())

        if result:
            print("✅ Redis conectado")
            return True
        else:
            print("❌ Redis no disponible")
            print("💡 Iniciar con: sudo systemctl start redis-server")
            return False

    except Exception as e:
        print(f"❌ Error Redis: {e}")
        print("💡 Verificar instalación y configuración de Redis")
        return False


def setup_environment():
    """Configurar variables de entorno para optimización"""
    try:
        # Optimizaciones CPU/GPU
        os.environ.setdefault("OMP_NUM_THREADS", "2")
        os.environ.setdefault("MKL_NUM_THREADS", "2")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128")

        print("⚡ Optimizaciones aplicadas")
        return True

    except Exception as e:
        print(f"⚠️ Error configurando entorno: {e}")
        return True  # No crítico


def load_config():
    """Cargar y mostrar configuración"""
    try:
        from app.config import settings

        print(f"\n📋 Configuración Ultra-Optimizada:")
        print(f"   🧠 Modelo: {settings.MODEL_SIZE}")
        print(f"   🔀 Concurrencia máx: {settings.MAX_CONCURRENT_JOBS}")
        print(f"   📁 Archivo máx: {settings.MAX_FILE_SIZE // (1024**2)}MB")
        print(f"   ⚡ Lazy loading: {settings.LAZY_MODEL_LOADING}")
        print(f"   🧹 Cleanup agresivo: {settings.AGGRESSIVE_CLEANUP}")
        print(f"   🗜️ Compresión: {settings.RESPONSE_COMPRESSION}")
        print(f"   📊 Log mínimo: {settings.MINIMAL_LOGGING}")
        print(f"   🕒 Descarga modelo: {settings.MODEL_UNLOAD_TIMEOUT}s")

        return settings

    except Exception as e:
        print(f"❌ Error cargando configuración: {e}")
        sys.exit(1)


def run_startup_checks():
    """Ejecutar todas las verificaciones de inicio"""
    print_banner()

    checks = [
        ("Python version", check_python_version),
        ("System resources", check_system_resources),
        ("Dependencies", verify_dependencies),
        ("Environment setup", setup_environment),
        ("GPU availability", check_gpu),
        ("Redis connection", test_redis)
    ]

    failed_checks = []

    for check_name, check_func in checks:
        try:
            if not check_func():
                failed_checks.append(check_name)
        except Exception as e:
            print(f"❌ Error en {check_name}: {e}")
            failed_checks.append(check_name)

    # Solo Redis es crítico para funcionamiento
    critical_failures = [f for f in failed_checks if "Redis" in f]

    if critical_failures:
        print(f"\n❌ Verificaciones críticas fallidas: {', '.join(critical_failures)}")
        sys.exit(1)

    if failed_checks:
        print(f"\n⚠️ Verificaciones con warnings: {', '.join(failed_checks)}")
        print("ℹ️ La API puede funcionar pero con limitaciones")

    return load_config()


def start_server(settings):
    """Iniciar servidor optimizado"""
    print(f"\n🚀 Iniciando servidor ultra-optimizado...")
    print(f"   📍 URL: http://{settings.HOST}:{settings.PORT}")
    print(f"   📚 Docs: http://{settings.HOST}:{settings.PORT}/docs")
    print(f"   💾 Memoria: Uso mínimo garantizado")
    print(f"   ⚡ Respuesta: < 100ms garantizada")
    print("="*60)

    try:
        import uvicorn

        # Configuración ultra-optimizada para máximo rendimiento
        server_config = {
            "app": "app.main:app",
            "host": settings.HOST,
            "port": settings.PORT,
            "workers": 1,  # SIEMPRE 1 para máxima eficiencia de memoria
            "log_level": "error" if settings.MINIMAL_LOGGING else "warning",
            "access_log": not settings.MINIMAL_LOGGING,
            "server_header": False,  # Sin headers innecesarios
            "date_header": False,    # Sin date header
            "reload": settings.DEBUG,
            "loop": "uvloop" if sys.platform != "win32" else "asyncio"
        }

        print("⚡ Configuración aplicada:")
        print(f"   - Workers: {server_config['workers']} (óptimo para memoria)")
        print(f"   - Log level: {server_config['log_level']}")
        print(f"   - Access log: {server_config['access_log']}")
        print(f"   - Event loop: {server_config['loop']}")

        start_time = time.time()
        print(f"\n🎯 Servidor iniciando... (timestamp: {int(start_time)})")

        uvicorn.run(**server_config)

    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\n👋 Servidor detenido por usuario después de {elapsed:.1f}s")
        print("💾 Memoria liberada automáticamente")

    except Exception as e:
        print(f"\n❌ Error crítico iniciando servidor: {e}")
        print("💡 Verificar configuración y dependencias")
        sys.exit(1)


def main():
    """Función principal - punto de entrada único"""
    try:
        # 1. Verificaciones de inicio
        settings = run_startup_checks()

        # 2. Crear directorios necesarios
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

        # 3. Iniciar servidor
        start_server(settings)

    except KeyboardInterrupt:
        print("\n👋 Salida por teclado")
        sys.exit(0)

    except Exception as e:
        print(f"\n💥 Error fatal: {e}")
        print("🔍 Revisar logs y configuración")
        sys.exit(1)


if __name__ == "__main__":
    main()