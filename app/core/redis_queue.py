import redis
import json
import time
from typing import Dict, List, Optional, Tuple, Any
from app.config import settings
from app.utils.logger import get_logger
from app.models.schemas import JobStatus

logger = get_logger(__name__)


class RedisJobQueue:
    """
    Sistema de colas Redis para manejar trabajos de transcripción
    Mantiene registro persistente de todos los trabajos
    """

    def __init__(self):
        """Inicializar conexión a Redis"""
        try:
            redis_config = {
                "host": settings.REDIS_HOST,
                "port": settings.REDIS_PORT,
                "db": settings.REDIS_DB,
                "decode_responses": True,
                "socket_connect_timeout": 5,
                "socket_timeout": 5,
                "retry_on_timeout": True
            }

            if settings.REDIS_PASSWORD:
                redis_config["password"] = settings.REDIS_PASSWORD

            self.redis = redis.Redis(**redis_config)

            # Verificar conexión
            self.redis.ping()
            logger.info("✅ Conectado a Redis exitosamente")

        except Exception as e:
            logger.error(f"❌ Error conectando a Redis: {e}")
            raise ConnectionError(f"No se pudo conectar a Redis: {e}")

        # Definir claves Redis organizadas
        self.keys = {
            "pending": "whisper:pending",           # Cola de trabajos pendientes
            "processing": "whisper:processing",     # Set de trabajos en proceso
            "completed": "whisper:completed",       # Lista de trabajos completados
            "failed": "whisper:failed",             # Lista de trabajos fallidos
            "jobs": "whisper:jobs",                 # Hash con datos de todos los trabajos
            "stats": "whisper:stats",               # Estadísticas globales
            "speeds": "whisper:speeds"              # Lista de velocidades recientes
        }

    def add_job(self, job_id: str, job_data: Dict[str, Any]) -> int:
        """
        Agregar trabajo a la cola
        Returns: posición en la cola
        """
        try:
            pipeline = self.redis.pipeline()

            # Preparar datos del trabajo
            job_data.update({
                "job_id": job_id,
                "status": JobStatus.PENDING,
                "created_at": time.time()
            })

            # Guardar datos del trabajo
            pipeline.hset(self.keys["jobs"], job_id, json.dumps(job_data))

            # Agregar a cola de pendientes (FIFO)
            pipeline.lpush(self.keys["pending"], job_id)

            # Incrementar contador total
            pipeline.hincrby(self.keys["stats"], "total_jobs", 1)

            # Ejecutar todas las operaciones
            pipeline.execute()

            # Obtener posición en cola
            position = self.redis.llen(self.keys["pending"])

            logger.info(f"Trabajo {job_id} agregado a cola (posición {position})")
            return position

        except Exception as e:
            logger.error(f"Error agregando trabajo {job_id}: {e}")
            raise

    def get_next_job(self, timeout: int = 5) -> Tuple[Optional[str], Optional[Dict]]:
        """
        Obtener siguiente trabajo de la cola (operación bloqueante)
        Returns: (job_id, job_data) o (None, None) si timeout
        """
        try:
            # Mover atómicamente de pending a processing
            job_id = self.redis.brpoplpush(
                self.keys["pending"],
                self.keys["processing"],
                timeout=timeout
            )

            if not job_id:
                return None, None

            # Obtener datos del trabajo
            job_data_str = self.redis.hget(self.keys["jobs"], job_id)
            if not job_data_str:
                logger.warning(f"No se encontraron datos para trabajo {job_id}")
                return None, None

            job_data = json.loads(job_data_str)

            # Actualizar estado a processing
            job_data.update({
                "status": JobStatus.PROCESSING,
                "started_at": time.time()
            })

            # Guardar cambios
            self.redis.hset(self.keys["jobs"], job_id, json.dumps(job_data))

            logger.info(f"Trabajo {job_id} obtenido para procesamiento")
            return job_id, job_data

        except Exception as e:
            logger.error(f"Error obteniendo trabajo: {e}")
            return None, None

    def update_job(self, job_id: str, updates: Dict[str, Any]):
        """Actualizar datos de un trabajo"""
        try:
            current_data_str = self.redis.hget(self.keys["jobs"], job_id)
            if current_data_str:
                job_data = json.loads(current_data_str)
                job_data.update(updates)
                self.redis.hset(self.keys["jobs"], job_id, json.dumps(job_data))
                logger.debug(f"Trabajo {job_id} actualizado")
            else:
                logger.warning(f"Trabajo {job_id} no encontrado para actualizar")
        except Exception as e:
            logger.error(f"Error actualizando trabajo {job_id}: {e}")

    def complete_job(self, job_id: str, result: Dict[str, Any], success: bool = True):
        """Marcar trabajo como completado o fallido"""
        try:
            pipeline = self.redis.pipeline()

            # Actualizar datos del trabajo
            result.update({
                "status": JobStatus.COMPLETED if success else JobStatus.FAILED,
                "completed_at": time.time()
            })

            self.update_job(job_id, result)

            # Remover de processing
            pipeline.lrem(self.keys["processing"], 0, job_id)

            # Agregar a lista correspondiente
            if success:
                pipeline.lpush(self.keys["completed"], job_id)
                pipeline.hincrby(self.keys["stats"], "completed_today", 1)

                # Registrar velocidad para estadísticas
                if "speed" in result:
                    pipeline.lpush(self.keys["speeds"], result["speed"])
                    pipeline.ltrim(self.keys["speeds"], 0, 99)  # Mantener últimas 100
            else:
                pipeline.lpush(self.keys["failed"], job_id)
                pipeline.hincrby(self.keys["stats"], "failed_today", 1)

            pipeline.execute()

            status_msg = "completado" if success else "fallido"
            logger.info(f"Trabajo {job_id} {status_msg}")

        except Exception as e:
            logger.error(f"Error completando trabajo {job_id}: {e}")

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Obtener datos de un trabajo específico"""
        try:
            job_data_str = self.redis.hget(self.keys["jobs"], job_id)
            if job_data_str:
                return json.loads(job_data_str)
            return None
        except Exception as e:
            logger.error(f"Error obteniendo trabajo {job_id}: {e}")
            return None

    def get_queue_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas de la cola"""
        try:
            # Contar trabajos en cada estado
            pending = self.redis.llen(self.keys["pending"])
            processing = self.redis.llen(self.keys["processing"])

            # Estadísticas acumuladas
            stats = self.redis.hgetall(self.keys["stats"])
            completed_today = int(stats.get("completed_today", 0))
            failed_today = int(stats.get("failed_today", 0))
            total_jobs = int(stats.get("total_jobs", 0))

            # Calcular velocidad promedio
            speeds = self.redis.lrange(self.keys["speeds"], 0, -1)
            average_speed = None
            if speeds:
                speeds_float = [float(s) for s in speeds]
                average_speed = sum(speeds_float) / len(speeds_float)

            return {
                "pending": pending,
                "processing": processing,
                "completed_today": completed_today,
                "failed_today": failed_today,
                "total_jobs": total_jobs,
                "average_speed": average_speed
            }

        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return {
                "pending": 0,
                "processing": 0,
                "completed_today": 0,
                "failed_today": 0,
                "total_jobs": 0,
                "average_speed": None
            }

    def get_pending_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtener lista de trabajos pendientes"""
        try:
            job_ids = self.redis.lrange(self.keys["pending"], 0, limit - 1)
            jobs = []

            for job_id in job_ids:
                job_data = self.get_job(job_id)
                if job_data:
                    jobs.append({
                        "job_id": job_id,
                        "filename": job_data.get("filename"),
                        "status": job_data.get("status"),
                        "created_at": job_data.get("created_at"),
                        "file_size": job_data.get("file_size")
                    })

            return jobs

        except Exception as e:
            logger.error(f"Error obteniendo trabajos pendientes: {e}")
            return []

    def get_recent_jobs(self, hours: int = 24, limit: int = 100) -> List[Dict[str, Any]]:
        """Obtener trabajos recientes (completados y fallidos)"""
        try:
            cutoff_time = time.time() - (hours * 3600)
            all_jobs = []

            # Obtener de listas de completados y fallidos
            for list_key in [self.keys["completed"], self.keys["failed"]]:
                job_ids = self.redis.lrange(list_key, 0, limit)

                for job_id in job_ids:
                    job_data = self.get_job(job_id)
                    if job_data and job_data.get("created_at", 0) > cutoff_time:
                        all_jobs.append(job_data)

            # Ordenar por created_at descendente
            all_jobs.sort(key=lambda x: x.get("created_at", 0), reverse=True)
            return all_jobs[:limit]

        except Exception as e:
            logger.error(f"Error obteniendo trabajos recientes: {e}")
            return []

    def get_job_position(self, job_id: str) -> Optional[int]:
        """Obtener posición de un trabajo en la cola de pendientes"""
        try:
            pending_jobs = self.redis.lrange(self.keys["pending"], 0, -1)
            if job_id in pending_jobs:
                return pending_jobs.index(job_id) + 1
            return None
        except Exception as e:
            logger.error(f"Error obteniendo posición del trabajo {job_id}: {e}")
            return None

    def delete_job(self, job_id: str) -> bool:
        """Eliminar trabajo completamente del sistema"""
        try:
            pipeline = self.redis.pipeline()

            # Remover de todas las listas
            pipeline.lrem(self.keys["pending"], 0, job_id)
            pipeline.lrem(self.keys["processing"], 0, job_id)
            pipeline.lrem(self.keys["completed"], 0, job_id)
            pipeline.lrem(self.keys["failed"], 0, job_id)

            # Remover datos del trabajo
            pipeline.hdel(self.keys["jobs"], job_id)

            results = pipeline.execute()

            # Verificar si se eliminó algo
            deleted = any(result > 0 for result in results[:-1]) or results[-1] > 0

            if deleted:
                logger.info(f"Trabajo {job_id} eliminado del sistema")
            else:
                logger.warning(f"Trabajo {job_id} no encontrado para eliminar")

            return deleted

        except Exception as e:
            logger.error(f"Error eliminando trabajo {job_id}: {e}")
            return False

    def cleanup_old_jobs(self, days: int = 7) -> int:
        """Limpiar trabajos antiguos"""
        try:
            cutoff_time = time.time() - (days * 24 * 3600)
            cleaned = 0

            # Revisar listas de completados y fallidos
            for list_key in [self.keys["completed"], self.keys["failed"]]:
                job_ids = self.redis.lrange(list_key, 0, -1)

                for job_id in job_ids:
                    job_data = self.get_job(job_id)
                    if job_data and job_data.get("created_at", 0) < cutoff_time:
                        if self.delete_job(job_id):
                            cleaned += 1

            logger.info(f"Limpiados {cleaned} trabajos antiguos (>{days} días)")
            return cleaned

        except Exception as e:
            logger.error(f"Error limpiando trabajos antiguos: {e}")
            return 0

    def reset_daily_stats(self):
        """Resetear estadísticas diarias (para cron job)"""
        try:
            pipeline = self.redis.pipeline()
            pipeline.hset(self.keys["stats"], "completed_today", 0)
            pipeline.hset(self.keys["stats"], "failed_today", 0)
            pipeline.execute()

            logger.info("Estadísticas diarias reseteadas")

        except Exception as e:
            logger.error(f"Error reseteando estadísticas diarias: {e}")

    def get_connection_info(self) -> Dict[str, Any]:
        """Información de conexión Redis"""
        try:
            info = self.redis.info()
            return {
                "connected": True,
                "redis_version": info.get("redis_version"),
                "used_memory_human": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "total_commands_processed": info.get("total_commands_processed")
            }
        except Exception as e:
            logger.error(f"Error obteniendo info de Redis: {e}")
            return {"connected": False, "error": str(e)}

    def health_check(self) -> bool:
        """Verificar salud de Redis"""
        try:
            self.redis.ping()
            return True
        except Exception:
            return False


# Instancia global de la cola
job_queue = RedisJobQueue()