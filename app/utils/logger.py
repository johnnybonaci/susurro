import logging
import sys
from pathlib import Path
from loguru import logger as loguru_logger
from app.config import settings


class InterceptHandler(logging.Handler):
    """Handler para interceptar logs de logging estándar y enviarlos a loguru"""

    def emit(self, record):
        # Obtener el nivel correspondiente en loguru
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Encontrar el frame del caller
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        loguru_logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging():
    """Configurar el sistema de logging"""

    # Remover el handler por defecto de loguru
    loguru_logger.remove()

    # Configurar formato
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Log a consola
    loguru_logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=log_format,
        colorize=True,
        backtrace=True,
        diagnose=True
    )

    # Log a archivo con rotación
    loguru_logger.add(
        settings.LOG_FILE,
        level=settings.LOG_LEVEL,
        format=log_format,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        compression="zip",
        backtrace=True,
        diagnose=True
    )

    # Interceptar logs de otras librerías
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Configurar logs específicos
    for logger_name in ["uvicorn", "uvicorn.access", "fastapi"]:
        logging.getLogger(logger_name).handlers = [InterceptHandler()]

    # Log inicial
    loguru_logger.info("Sistema de logging configurado")
    loguru_logger.info(f"Nivel de log: {settings.LOG_LEVEL}")
    loguru_logger.info(f"Archivo de log: {settings.LOG_FILE}")


def get_logger(name: str):
    """Obtener logger para un módulo específico"""
    return loguru_logger.bind(name=name)


# Configurar logging al importar
setup_logging()
