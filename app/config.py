import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # === CONFIGURACIÓN WHISPER ===
    MODEL_SIZE: str = "small"
    MAX_CONCURRENT_JOBS: int = 3
    MAX_FILE_SIZE: int = 500 * 1024 * 1024  # 500MB
    UPLOAD_DIR: str = "temp_uploads"

    # === CONFIGURACIÓN WHISPER OPTIMIZADA ===
    BEAM_SIZE: int = 1
    BEST_OF: int = 1
    TEMPERATURE: float = 0.0
    VAD_FILTER: bool = True
    MIN_SILENCE_DURATION_MS: int = 300
    VAD_THRESHOLD: float = 0.4
    CHUNK_LENGTH: int = 30
    CONDITION_ON_PREVIOUS_TEXT: bool = False
    COMPRESSION_RATIO_THRESHOLD: float = 2.4
    LOG_PROB_THRESHOLD: float = -1.0
    NO_SPEECH_THRESHOLD: float = 0.6

    # === CONFIGURACIÓN GPU ===
    DEVICE: str = "cuda"
    COMPUTE_TYPE: str = "float16"
    NUM_WORKERS: int = 1
    DEVICE_INDEX: int = 0
    CPU_THREADS: int = 4

    # === CONFIGURACIÓN REDIS ===
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # === CONFIGURACIÓN API ===
    API_TITLE: str = "Whisper Transcription API"
    API_DESCRIPTION: str = "API de transcripción de audio con Faster Whisper"
    API_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # === CONFIGURACIÓN SERVIDOR ===
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1

    # === CONFIGURACIÓN LOGS ===
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "whisper-api.log"
    LOG_ROTATION: str = "1 day"
    LOG_RETENTION: str = "7 days"

    # === CONFIGURACIÓN ARCHIVOS ===
    ALLOWED_EXTENSIONS: list = [".mp3", ".wav", ".m4a", ".flac", ".ogg"]
    CLEANUP_INTERVAL_HOURS: int = 24
    CLEANUP_AGE_DAYS: int = 7

    class Config:
        env_file = ".env"
        case_sensitive = True


# Instancia global de configuración
settings = Settings()

# Crear directorio de uploads si no existe
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
