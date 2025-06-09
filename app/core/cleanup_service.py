import os
import time
import asyncio
import glob
from pathlib import Path
from typing import List

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CleanupService:
    """
    Servicio de limpieza automática de archivos temporales
    """

    def __init__(self):
        self.cleanup_interval = 300  # 5 minutos
        self.max_file_age = settings.TEMP_FILE_CLEANUP * 60  # Convertir a segundos
        self.running = False
        self._cleanup_task = None

    async def start_cleanup_task(self):
        """Iniciar tarea de limpieza en background"""
        if self.running:
            return

        self.running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"🧹 Servicio de limpieza iniciado (cada {self.cleanup_interval}s)")

    async def stop_cleanup_task(self):
        """Detener tarea de limpieza"""
        self.running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Servicio de limpieza detenido")

    async def _cleanup_loop(self):
        """Loop principal de limpieza"""
        while self.running:
            try:
                await self.cleanup_temp_files()
                await asyncio.sleep(self.cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error en cleanup loop: {e}")
                await asyncio.sleep(60)  # Esperar 1 minuto antes de reintentar

    async def cleanup_temp_files(self) -> int:
        """
        Limpiar archivos temporales antiguos
        
        Returns:
            Número de archivos eliminados
        """
        try:
            upload_dir = Path(settings.UPLOAD_DIR)
            if not upload_dir.exists():
                return 0

            current_time = time.time()
            files_deleted = 0
            total_size_deleted = 0

            # Buscar todos los archivos en el directorio de uploads
            for file_path in upload_dir.iterdir():
                if file_path.is_file():
                    try:
                        # Verificar edad del archivo
                        file_age = current_time - file_path.stat().st_mtime
                        
                        if file_age > self.max_file_age:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            files_deleted += 1
                            total_size_deleted += file_size
                            
                            logger.debug(f"🗑️ Eliminado: {file_path.name} ({file_size} bytes, {file_age/60:.1f}min)")
                    
                    except Exception as e:
                        logger.warning(f"⚠️ Error eliminando {file_path.name}: {e}")

            if files_deleted > 0:
                size_mb = total_size_deleted / (1024 * 1024)
                logger.info(f"🧹 Cleanup: {files_deleted} archivos eliminados ({size_mb:.1f}MB liberados)")

            return files_deleted

        except Exception as e:
            logger.error(f"❌ Error en cleanup_temp_files: {e}")
            return 0

    async def cleanup_old_files_by_pattern(self, pattern: str = "*") -> int:
        """
        Limpiar archivos específicos por patrón
        
        Args:
            pattern: Patrón de archivos a buscar (ej: "*.mp3", "temp_*")
            
        Returns:
            Número de archivos eliminados
        """
        try:
            upload_dir = Path(settings.UPLOAD_DIR)
            if not upload_dir.exists():
                return 0

            current_time = time.time()
            files_deleted = 0

            # Buscar archivos por patrón
            for file_path in upload_dir.glob(pattern):
                if file_path.is_file():
                    try:
                        file_age = current_time - file_path.stat().st_mtime
                        
                        if file_age > self.max_file_age:
                            file_path.unlink()
                            files_deleted += 1
                            logger.debug(f"🗑️ Eliminado por patrón: {file_path.name}")
                    
                    except Exception as e:
                        logger.warning(f"⚠️ Error eliminando {file_path.name}: {e}")

            return files_deleted

        except Exception as e:
            logger.error(f"❌ Error en cleanup por patrón: {e}")
            return 0

    async def force_cleanup_all(self) -> int:
        """
        Forzar limpieza de TODOS los archivos temporales
        (independientemente de la edad)
        
        Returns:
            Número de archivos eliminados
        """
        try:
            upload_dir = Path(settings.UPLOAD_DIR)
            if not upload_dir.exists():
                return 0

            files_deleted = 0
            total_size = 0

            for file_path in upload_dir.iterdir():
                if file_path.is_file():
                    try:
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        files_deleted += 1
                        total_size += file_size
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Error eliminando {file_path.name}: {e}")

            if files_deleted > 0:
                size_mb = total_size / (1024 * 1024)
                logger.info(f"🧹 Cleanup forzado: {files_deleted} archivos ({size_mb:.1f}MB)")

            return files_deleted

        except Exception as e:
            logger.error(f"❌ Error en force_cleanup: {e}")
            return 0

    async def get_temp_files_info(self) -> dict:
        """
        Obtener información sobre archivos temporales
        
        Returns:
            Dict con estadísticas de archivos temporales
        """
        try:
            upload_dir = Path(settings.UPLOAD_DIR)
            if not upload_dir.exists():
                return {
                    "total_files": 0,
                    "total_size_mb": 0,
                    "old_files": 0,
                    "old_files_size_mb": 0
                }

            current_time = time.time()
            total_files = 0
            total_size = 0
            old_files = 0
            old_files_size = 0

            for file_path in upload_dir.iterdir():
                if file_path.is_file():
                    try:
                        file_size = file_path.stat().st_size
                        file_age = current_time - file_path.stat().st_mtime
                        
                        total_files += 1
                        total_size += file_size
                        
                        if file_age > self.max_file_age:
                            old_files += 1
                            old_files_size += file_size
                            
                    except Exception as e:
                        logger.warning(f"⚠️ Error analizando {file_path.name}: {e}")

            return {
                "total_files": total_files,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "old_files": old_files,
                "old_files_size_mb": round(old_files_size / (1024 * 1024), 2),
                "cleanup_age_minutes": self.max_file_age / 60
            }

        except Exception as e:
            logger.error(f"❌ Error obteniendo info temp files: {e}")
            return {
                "total_files": 0,
                "total_size_mb": 0,
                "old_files": 0,
                "old_files_size_mb": 0,
                "error": str(e)
            }

    def update_cleanup_settings(self, cleanup_minutes: int = None, interval_seconds: int = None):
        """
        Actualizar configuración de limpieza dinámicamente
        
        Args:
            cleanup_minutes: Nueva edad máxima de archivos en minutos
            interval_seconds: Nuevo intervalo de limpieza en segundos
        """
        if cleanup_minutes is not None and cleanup_minutes > 0:
            self.max_file_age = cleanup_minutes * 60
            logger.info(f"🔧 Edad máxima archivos actualizada: {cleanup_minutes} minutos")

        if interval_seconds is not None and interval_seconds >= 60:
            self.cleanup_interval = interval_seconds
            logger.info(f"🔧 Intervalo cleanup actualizado: {interval_seconds} segundos")


# Instancia global del servicio de limpieza
cleanup_service = CleanupService()