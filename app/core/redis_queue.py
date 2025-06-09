import redis
import json
import time
import asyncio
from typing import Dict, List, Optional, Any
from enum import Enum

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OptimizedRedisQueue:
    """
    Cola Redis ultra-optimizada con TTL automático
    Mínima memoria, máxima velocidad
    """

    def __init__(self):
        try:
            # Configuración Redis optimizada
            self.redis = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=2,  # Timeout reducido
                socket_timeout=2,
                health_check_interval=30,
                max_connections=10  # Pool pequeño
            )

            # Test de conexión
            self.redis.ping()
            logger.info("✅ Redis conectado")

        except Exception as e:
            logger.error(f"❌ Error Redis: {e}")
            raise ConnectionError(f"Redis no disponible: {e}")

        # Claves Redis minimalistas
        self.keys = {
            "pending": "wq:pending",
            "processing": "wq:processing",
            "jobs": "wq:jobs:",  # Prefix para jobs individuales
            "stats": "wq:stats"
        }

    async def add_job(self, job_id: str, job_data: Dict[str, Any]) -> int:
        """Agregar trabajo con TTL automático"""
        try:
            # Preparar datos mínimos
            job_data.update({
                "job_id": job_id,
                "status": JobStatus.PENDING,
                "created_at": time.time()
            })

            # Pipeline para operaciones atómicas
            pipe = self.redis.pipeline()

            # Guardar job con TTL
            job_key = f"{self.keys['jobs']}{job_id}"
            pipe.setex(job_key, settings.JOB_TTL, json.dumps(job_data))

            # Agregar a cola de pendientes
            pipe.lpush(self.keys["pending"], job_id)

            # Stats mínimos
            pipe.hincrby(self.keys["stats"], "total", 1)

            # Ejecutar pipeline
            pipe.execute()

            # Posición en cola
            position = self.redis.llen(self.keys["pending"])

            logger.info(f"📝 Job {job_id} en posición {position}")
            return position

        except Exception as e:
            logger.error(f"❌ Error agregando job {job_id}: {e}")
            raise

    async def get_next_job(self) -> Optional[Dict[str, Any]]:
        """Obtener siguiente trabajo (no bloqueante)"""
        try:
            # Mover atómicamente a processing
            job_id = self.redis.rpoplpush(
                self.keys["pending"],
                self.keys["processing"]
            )

            if not job_id:
                return None

            # Obtener datos del job
            job_key = f"{self.keys['jobs']}{job_id}"
            job_data_str = self.redis.get(job_key)

            if not job_data_str:
                # Job expiró, limpiar
                self.redis.lrem(self.keys["processing"], 0, job_id)
                return None

            job_data = json.loads(job_data_str)

            # Actualizar estado
            job_data.update({
                "status": JobStatus.PROCESSING,
                "started_at": time.time()
            })

            # Guardar cambios con TTL extendido
            self.redis.setex(job_key, settings.JOB_TTL, json.dumps(job_data))

            logger.info(f"🔄 Procesando job {job_id}")
            return job_data

        except Exception as e:
            logger.error(f"❌ Error obteniendo job: {e}")
            return None

    async def complete_job(self, job_id: str, result: Dict[str, Any], success: bool = True):
        """Completar trabajo con TTL para resultado"""
        try:
            job_key = f"{self.keys['jobs']}{job_id}"

            # Actualizar estado
            result.update({
                "status": JobStatus.COMPLETED if success else JobStatus.FAILED,
                "completed_at": time.time()
            })

            pipe = self.redis.pipeline()

            # Guardar resultado con TTL más corto
            ttl = settings.RESULT_TTL if success else 300  # 5 min para errores
            pipe.setex(job_key, ttl, json.dumps(result))

            # Remover de processing
            pipe.lrem(self.keys["processing"], 0, job_id)

            # Stats
            stat_key = "completed" if success else "failed"
            pipe.hincrby(self.keys["stats"], stat_key, 1)

            pipe.execute()

            status_msg = "✅ completado" if success else "❌ fallido"
            logger.info(f"{status_msg}: {job_id}")

        except Exception as e:
            logger.error(f"❌ Error completando job {job_id}: {e}")

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Obtener datos de trabajo"""
        try:
            job_key = f"{self.keys['jobs']}{job_id}"
            job_data_str = self.redis.get(job_key)

            if job_data_str:
                return json.loads(job_data_str)
            return None

        except Exception as e:
            logger.error(f"❌ Error obteniendo job {job_id}: {e}")
            return None

    async def get_queue_status(self) -> Dict[str, Any]:
        """Estado rápido de la cola"""
        try:
            pipe = self.redis.pipeline()

            # Conteos básicos
            pipe.llen(self.keys["pending"])
            pipe.llen(self.keys["processing"])
            pipe.hgetall(self.keys["stats"])

            results = pipe.execute()

            pending = results[0]
            processing = results[1]
            stats = results[2]

            return {
                "pending": pending,
                "processing": processing,
                "completed": int(stats.get("completed", 0)),
                "failed": int(stats.get("failed", 0)),
                "total": int(stats.get("total", 0)),
                "can_accept": processing < settings.MAX_CONCURRENT_JOBS
            }

        except Exception as e:
            logger.error(f"❌ Error stats: {e}")
            return {
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
                "total": 0,
                "can_accept": False
            }

    async def get_job_position(self, job_id: str) -> Optional[int]:
        """Posición en cola de forma eficiente"""
        try:
            # Obtener lista de pendientes
            pending_jobs = self.redis.lrange(self.keys["pending"], 0, -1)

            if job_id in pending_jobs:
                return len(pending_jobs) - pending_jobs.index(job_id)
            return None

        except Exception as e:
            logger.error(f"❌ Error posición job {job_id}: {e}")
            return None

    async def health_check(self) -> bool:
        """Health check rápido"""
        try:
            self.redis.ping()
            return True
        except:
            return False

    async def cleanup_expired(self) -> int:
        """Limpiar trabajos expirados de las colas"""
        try:
            cleaned = 0

            # Limpiar pending jobs expirados
            pending_jobs = self.redis.lrange(self.keys["pending"], 0, -1)
            for job_id in pending_jobs:
                job_key = f"{self.keys['jobs']}{job_id}"
                if not self.redis.exists(job_key):
                    self.redis.lrem(self.keys["pending"], 0, job_id)
                    cleaned += 1

            # Limpiar processing jobs expirados
            processing_jobs = self.redis.lrange(self.keys["processing"], 0, -1)
            for job_id in processing_jobs:
                job_key = f"{self.keys['jobs']}{job_id}"
                if not self.redis.exists(job_key):
                    self.redis.lrem(self.keys["processing"], 0, job_id)
                    cleaned += 1

            if cleaned > 0:
                logger.info(f"🧹 Limpiados {cleaned} jobs expirados")

            return cleaned

        except Exception as e:
            logger.error(f"❌ Error cleanup: {e}")
            return 0

    async def reset_stats(self):
        """Reset stats (para maintenance)"""
        try:
            self.redis.delete(self.keys["stats"])
            logger.info("📊 Stats reseteadas")
        except Exception as e:
            logger.error(f"❌ Error reset stats: {e}")


# Instancia global
job_queue = OptimizedRedisQueue()