import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # === CONFIGURACIÓN WHISPER OPTIMIZADA ===
    MODEL_SIZE: str = "small"
    MAX_CONCURRENT_JOBS: int = 1  # Dinámico: 1-3
    MAX_FILE_SIZE: int = 25 * 1024 * 1024  # 25MB (reducido)
    UPLOAD_DIR: str = "temp_uploads"

    # === OPTIMIZACIÓN MEMORIA EXTREMA ===
    LAZY_MODEL_LOADING: bool = True  # Cargar/descargar bajo demanda
    MODEL_UNLOAD_TIMEOUT: int = 30  # Segundos antes de descargar modelo
    AGGRESSIVE_CLEANUP: bool = True  # Limpieza agresiva post-transcripción
    STREAM_FILE_THRESHOLD: int = 5 * 1024 * 1024  # 5MB - streaming por encima

    # === WHISPER CONFIGURACIÓN MÍNIMA ===
    BEAM_SIZE: int = 1
    TEMPERATURE: float = 0.0
    VAD_FILTER: bool = True
    CHUNK_LENGTH: int = 30
    CONDITION_ON_PREVIOUS_TEXT: bool = False

    # === GPU/CPU OPTIMIZADO ===
    DEVICE: str = "cuda"
    COMPUTE_TYPE: str = "float16"  # Mínimo para GPU
    CPU_THREADS: int = 2  # Reducido

    # === REDIS MINIMALISTA ===
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    JOB_TTL: int = 3600  # TTL automático 1 hora
    RESULT_TTL: int = 1800  # Resultados 30 min

    # === API ULTRA-RÁPIDA ===
    RESPONSE_COMPRESSION: bool = True
    FAST_VALIDATION: bool = True
    MINIMAL_LOGGING: bool = True

    # === SERVIDOR LIGERO ===
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1  # Siempre 1 para máxima eficiencia

    # === ARCHIVOS ===
    ALLOWED_EXTENSIONS: list = [".mp3", ".wav", ".m4a", ".flac", ".ogg"]
    TEMP_FILE_CLEANUP: int = 10  # Minutos para limpiar archivos temp

    # === LOGS MÍNIMOS ===
    LOG_LEVEL: str = "WARNING"  # Solo errores importantes
    LOG_FILE: Optional[str] = None  # Sin archivo por defecto
    DEBUG: bool = False  # Modo debug

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignorar campos extra en .env

    def update_concurrency(self, new_value: int):
        """Actualizar concurrencia dinámicamente"""
        if 1 <= new_value <= 3:
            self.MAX_CONCURRENT_JOBS = new_value
            return True
        return False


# Instancia global
settings = Settings()

# Crear directorio uploads si no existe
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)