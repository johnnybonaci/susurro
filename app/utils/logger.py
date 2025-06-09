import logging
import sys
from app.config import settings


class MinimalLogger:
    """Logger ultra-minimalista para máximo rendimiento"""

    def __init__(self, name: str):
        self.name = name
        self.level = getattr(logging, settings.LOG_LEVEL.upper(), logging.WARNING)

        # Solo configurar una vez
        if not hasattr(MinimalLogger, '_configured'):
            self._setup_logging()
            MinimalLogger._configured = True

    def _setup_logging(self):
        """Configuración mínima de logging"""

        # Formato ultra-simple
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )

        # Handler a consola
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(self.level)

        # Logger raíz
        root_logger = logging.getLogger()
        root_logger.setLevel(self.level)
        root_logger.handlers.clear()  # Limpiar handlers existentes
        root_logger.addHandler(console_handler)

        # Silenciar loggers verbosos
        logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
        logging.getLogger("multipart").setLevel(logging.ERROR)

        if settings.MINIMAL_LOGGING:
            # En modo minimal, solo errores críticos
            root_logger.setLevel(logging.ERROR)

    def info(self, message: str):
        if self.level <= logging.INFO:
            print(f"[INFO] {message}")

    def warning(self, message: str):
        if self.level <= logging.WARNING:
            print(f"[WARN] {message}")

    def error(self, message: str):
        if self.level <= logging.ERROR:
            print(f"[ERROR] {message}")

    def debug(self, message: str):
        if self.level <= logging.DEBUG:
            print(f"[DEBUG] {message}")


def get_logger(name: str) -> MinimalLogger:
    """Obtener logger minimalista"""
    return MinimalLogger(name)