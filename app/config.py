import os
from typing import Optional, List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # === CONFIGURACIÓN WHISPER OPTIMIZADA ===
    MODEL_SIZE: str = "small"
    MAX_CONCURRENT_JOBS: int = 1  # Dinámico: 1-3
    MAX_FILE_SIZE: int = 25 * 1024 * 1024  # 25MB (reducido)
    UPLOAD_DIR: str = "temp_uploads"

    # === OPTIMIZACIÓN MEMORIA EXTREMA ===
    LAZY_MODEL_LOADING: bool = False  # Always-loaded mode por defecto
    MODEL_UNLOAD_TIMEOUT: int = 999999  # Nunca descargar en always-loaded
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
    MINIMAL_LOGGING: bool = False  # Cambiado para mejor debugging

    # === SERVIDOR LIGERO ===
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1  # Siempre 1 para máxima eficiencia

    # === ARCHIVOS ===
    ALLOWED_EXTENSIONS: List[str] = [".mp3", ".wav", ".m4a", ".flac", ".ogg"]
    TEMP_FILE_CLEANUP: int = 10  # Minutos para limpiar archivos temp

    # === LOGS MÍNIMOS ===
    LOG_LEVEL: str = "INFO"  # Cambiado de WARNING para mejor debugging
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

    @property
    def is_always_loaded_mode(self) -> bool:
        """Verificar si está en modo always-loaded"""
        return not self.LAZY_MODEL_LOADING and self.MODEL_UNLOAD_TIMEOUT > 86400

    def get_device_config(self) -> dict:
        """Obtener configuración del dispositivo"""
        config = {
            "device": self.DEVICE,
            "compute_type": self.COMPUTE_TYPE
        }

        if self.DEVICE == "cuda":
            config["device_index"] = 0

        return config

    def get_whisper_config(self) -> dict:
        """Obtener configuración de Whisper"""
        return {
            "beam_size": self.BEAM_SIZE,
            "temperature": self.TEMPERATURE,
            "vad_filter": self.VAD_FILTER,
            "chunk_length": self.CHUNK_LENGTH,
            "condition_on_previous_text": self.CONDITION_ON_PREVIOUS_TEXT
        }


# Instancia global
settings = Settings()

# Crear directorio uploads si no existe
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

# Configurar dispositivo automáticamente
try:
    import torch
    if not torch.cuda.is_available() and settings.DEVICE == "cuda":
        print("⚠️ CUDA no disponible, cambiando a CPU")
        settings.DEVICE = "cpu"
        settings.COMPUTE_TYPE = "int8"  # Más eficiente para CPU
except ImportError:
    print("⚠️ PyTorch no disponible, usando CPU por defecto")
    settings.DEVICE = "cpu"
    settings.COMPUTE_TYPE = "int8"