import redis
import json
import time
import asyncio
from typing import Optional, Dict, Any
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ProcessingSemaphore:
    """
    Semáforo Redis para control robusto de estado de procesamiento
    Garantiza que solo un proceso se ejecute a la vez
    """

    def __init__(self):
        try:
            # Conexión Redis optimizada
            self.redis = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                health_check_interval=30,
                max_connections=5
            )

            # Test conexión
            self.redis.ping()
            logger.info("✅ Redis semáforo conectado")

        except Exception as e:
            logger.error(f"❌ Error Redis semáforo: {e}")
            raise ConnectionError(f"Redis no disponible: {e}")

        # Claves Redis para el semáforo
        self.keys = {
            "lock": "whisper:processing_lock",
            "status": "whisper:current_status",
            "job_info": "whisper:current_job"
        }

        # TTL para auto-limpieza en caso de crash
        self.lock_ttl = 3600  # 1 hora máximo

    async def acquire_lock(self, job_id: str, job_info: Dict[str, Any]) -> bool:
        """
        Intentar adquirir el lock de procesamiento

        Returns:
            True: Lock adquirido, puede procesar
            False: Ya hay otro proceso ejecutándose
        """
        try:
            # Usar SET con NX (solo si no existe) y EX (con TTL)
            lock_acquired = self.redis.set(
                self.keys["lock"],
                job_id,
                nx=True,  # Solo si no existe
                ex=self.lock_ttl  # TTL de seguridad
            )

            if lock_acquired:
                # Lock adquirido, guardar info del job
                job_data = {
                    "job_id": job_id,
                    "start_time": time.time(),
                    "filename": job_info.get("filename"),
                    "file_size": job_info.get("file_size"),
                    "status": "processing"
                }

                # Guardar estado con TTL
                self.redis.setex(
                    self.keys["status"],
                    self.lock_ttl,
                    json.dumps(job_data)
                )

                logger.info(f"🔒 Lock adquirido para job {job_id}")
                return True
            else:
                logger.info(f"⏳ Lock no disponible para job {job_id}")
                return False

        except Exception as e:
            logger.error(f"❌ Error adquiriendo lock: {e}")
            return False

    async def release_lock(self, job_id: str) -> bool:
        """
        Liberar el lock de procesamiento

        Args:
            job_id: ID del job que libera el lock

        Returns:
            True: Lock liberado correctamente
            False: Error o job_id no coincide
        """
        try:
            # Verificar que el lock es nuestro usando script Lua (atómico)
            lua_script = """
            if redis.call("GET", KEYS[1]) == ARGV[1] then
                redis.call("DEL", KEYS[1])
                redis.call("DEL", KEYS[2])
                return 1
            else
                return 0
            end
            """

            result = self.redis.eval(
                lua_script,
                2,  # Número de keys
                self.keys["lock"], self.keys["status"],  # KEYS[1], KEYS[2]
                job_id  # ARGV[1]
            )

            if result == 1:
                logger.info(f"🔓 Lock liberado para job {job_id}")
                return True
            else:
                logger.warning(f"⚠️ No se pudo liberar lock para job {job_id} (no era propietario)")
                return False

        except Exception as e:
            logger.error(f"❌ Error liberando lock: {e}")
            return False

    async def get_current_status(self) -> Optional[Dict[str, Any]]:
        """
        Obtener estado actual del procesamiento

        Returns:
            Dict con estado actual o None si no hay procesamiento
        """
        try:
            # Verificar si hay lock activo
            current_lock = self.redis.get(self.keys["lock"])

            if not current_lock:
                return None

            # Obtener estado detallado
            status_data = self.redis.get(self.keys["status"])

            if status_data:
                job_data = json.loads(status_data)

                # Calcular tiempo transcurrido
                elapsed = time.time() - job_data.get("start_time", time.time())
                job_data["elapsed_seconds"] = round(elapsed, 1)

                # Estimar tiempo restante basado en tamaño del archivo
                file_size_mb = job_data.get("file_size", 0) / (1024 * 1024)
                estimated_total = max(30, file_size_mb * 2)  # ~2s por MB
                remaining = max(5, estimated_total - elapsed)
                job_data["estimated_remaining_seconds"] = round(remaining, 1)

                return job_data
            else:
                # Solo tenemos lock pero no estado detallado
                return {
                    "job_id": current_lock,
                    "status": "processing",
                    "elapsed_seconds": 0,
                    "estimated_remaining_seconds": 30
                }

        except Exception as e:
            logger.error(f"❌ Error obteniendo estado: {e}")
            return None

    async def is_processing(self) -> bool:
        """
        Verificar rápidamente si hay procesamiento activo

        Returns:
            True: Hay procesamiento en curso
            False: Sistema disponible
        """
        try:
            return self.redis.exists(self.keys["lock"]) == 1
        except Exception as e:
            logger.error(f"❌ Error verificando estado: {e}")
            return False  # Asumir disponible en caso de error

    async def force_release(self) -> bool:
        """
        Forzar liberación del lock (para casos de emergencia)

        Returns:
            True: Lock liberado
            False: Error
        """
        try:
            # Eliminar todas las claves relacionadas
            pipe = self.redis.pipeline()
            pipe.delete(self.keys["lock"])
            pipe.delete(self.keys["status"])
            pipe.execute()

            logger.info("🚨 Lock forzadamente liberado")
            return True

        except Exception as e:
            logger.error(f"❌ Error forzando liberación: {e}")
            return False

    async def health_check(self) -> bool:
        """
        Verificar salud del semáforo Redis

        Returns:
            True: Redis funcionando correctamente
            False: Problemas de conexión
        """
        try:
            self.redis.ping()
            return True
        except Exception:
            return False

    async def get_lock_ttl(self) -> Optional[int]:
        """
        Obtener TTL restante del lock actual

        Returns:
            Segundos restantes del lock o None si no hay lock
        """
        try:
            ttl = self.redis.ttl(self.keys["lock"])
            return ttl if ttl > 0 else None
        except Exception as e:
            logger.error(f"❌ Error obteniendo TTL: {e}")
            return None

    async def cleanup_expired(self) -> bool:
        """
        Limpiar locks expirados manualmente
        """
        try:
            # Redis ya maneja TTL automáticamente, pero podemos verificar
            if not await self.is_processing():
                # No hay procesamiento, limpiar cualquier estado residual
                pipe = self.redis.pipeline()
                pipe.delete(self.keys["status"])
                pipe.execute()
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Error cleanup: {e}")
            return False


# Instancia global del semáforo
processing_semaphore = ProcessingSemaphore()