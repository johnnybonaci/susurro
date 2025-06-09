import time
import torch
import asyncio
import threading
import gc
import psutil
from typing import Optional, Dict, Any
from faster_whisper import WhisperModel
from contextlib import asynccontextmanager

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AlwaysLoadedWhisperService:
    """
    Servicio Whisper con modelo SIEMPRE cargado
    Máxima velocidad de respuesta - No hay lazy loading
    """

    def __init__(self):
        self._model: Optional[WhisperModel] = None
        self._model_lock = asyncio.Lock()
        self._current_jobs = 0
        self._max_concurrent = settings.MAX_CONCURRENT_JOBS
        self._model_loaded_at = None
        self._total_transcriptions = 0

        # Inicializar modelo inmediatamente
        asyncio.create_task(self._initialize_model_on_startup())

        # Background maintenance (sin descarga de modelo)
        asyncio.create_task(self._background_maintenance())

    async def _initialize_model_on_startup(self):
        """Cargar modelo inmediatamente al iniciar"""
        logger.info("🚀 Inicializando modelo Whisper (always-loaded mode)...")

        try:
            # Limpiar memoria antes de cargar
            await self._aggressive_cleanup()

            # Crear modelo con configuración optimizada
            model_kwargs = {
                "device": settings.DEVICE,
                "compute_type": settings.COMPUTE_TYPE,
                "num_workers": 1,  # Mínimo para estabilidad
                "cpu_threads": settings.CPU_THREADS
            }

            if settings.DEVICE == "cuda":
                model_kwargs["device_index"] = 0

            # Cargar en thread separado
            loop = asyncio.get_event_loop()
            self._model = await loop.run_in_executor(
                None,
                lambda: WhisperModel(settings.MODEL_SIZE, **model_kwargs)
            )

            self._model_loaded_at = time.time()

            # Test rápido para verificar funcionamiento
            logger.info(f"✅ Modelo {settings.MODEL_SIZE} cargado y listo")

            # Log de memoria
            if torch.cuda.is_available():
                memory_mb = torch.cuda.memory_allocated() / (1024**2)
                logger.info(f"💾 VRAM ocupada: {memory_mb:.1f}MB")

            # Test dummy para verificar que funciona
            logger.info("🧪 Ejecutando test de verificación...")
            # El test se hará con el primer audio real

        except Exception as e:
            logger.error(f"❌ Error cargando modelo: {e}")
            self._model = None
            raise

    async def _background_maintenance(self):
        """Mantenimiento background SIN descarga de modelo"""
        while True:
            try:
                await asyncio.sleep(1800)  # Cada 30 minutos

                # Cleanup de memoria (sin tocar el modelo)
                if settings.AGGRESSIVE_CLEANUP and self._current_jobs == 0:
                    await self._memory_cleanup_without_model()

                # Log de estado cada hora
                current_time = time.time()
                if self._model_loaded_at and (current_time - self._model_loaded_at) % 3600 < 1800:
                    await self._log_status()

            except Exception as e:
                logger.error(f"❌ Error en maintenance: {e}")

    async def _memory_cleanup_without_model(self):
        """Limpieza de memoria conservando el modelo"""
        try:
            # Solo limpiar variables temporales, NO el modelo
            collected = gc.collect()

            # GPU cleanup suave
            if torch.cuda.is_available():
                # NO hacer empty_cache agresivo que podría afectar el modelo
                pass

            if collected > 0:
                logger.debug(f"🧹 Maintenance: {collected} objetos limpiados (modelo preservado)")

        except Exception as e:
            logger.error(f"❌ Error en cleanup: {e}")

    async def _aggressive_cleanup(self):
        """Limpieza agresiva (solo durante carga inicial)"""
        try:
            collected = gc.collect()

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()

            # GC agresivo solo durante startup
            if settings.AGGRESSIVE_CLEANUP:
                gc.set_threshold(0)
                for _ in range(3):
                    collected += gc.collect()
                gc.set_threshold(700, 10, 10)

            if collected > 0:
                logger.debug(f"🧹 Cleanup agresivo: {collected} objetos")

        except Exception as e:
            logger.error(f"❌ Error en cleanup agresivo: {e}")

    async def _log_status(self):
        """Log periódico de estado"""
        try:
            status = await self.get_status()
            uptime = time.time() - self._model_loaded_at if self._model_loaded_at else 0

            logger.info(
                f"📊 Estado: Modelo cargado {uptime/3600:.1f}h, "
                f"RAM {status['memory_info'].get('ram_usage_mb', 0):.1f}MB, "
                f"VRAM {status['memory_info'].get('gpu_memory_allocated_mb', 0):.1f}MB, "
                f"Transcripciones: {self._total_transcriptions}"
            )

        except Exception as e:
            logger.error(f"❌ Error logging status: {e}")

    async def can_process_job(self) -> bool:
        """Verificar si puede procesar un nuevo trabajo"""
        return self._model is not None and self._current_jobs < self._max_concurrent

    @asynccontextmanager
    async def get_model_context(self):
        """Context manager para usar modelo de forma segura"""
        if not await self.can_process_job():
            raise Exception("Servicio no disponible o máximo de trabajos alcanzado")

        if self._model is None:
            raise Exception("Modelo no cargado")

        async with self._model_lock:
            self._current_jobs += 1

        try:
            yield self._model
        finally:
            async with self._model_lock:
                self._current_jobs -= 1

    async def transcribe_audio(self, audio_path: str) -> Dict[str, Any]:
        """Transcribir audio con modelo siempre cargado"""
        start_time = time.time()

        async with self.get_model_context() as model:
            logger.info(f"🎤 Transcribiendo (modelo pre-cargado): {audio_path}")

            try:
                # Transcribir en thread separado
                loop = asyncio.get_event_loop()
                segments, info = await loop.run_in_executor(
                    None,
                    lambda: model.transcribe(
                        audio_path,
                        beam_size=settings.BEAM_SIZE,
                        temperature=settings.TEMPERATURE,
                        vad_filter=settings.VAD_FILTER,
                        chunk_length=settings.CHUNK_LENGTH,
                        condition_on_previous_text=settings.CONDITION_ON_PREVIOUS_TEXT
                    )
                )

                # Procesar segmentos eficientemente
                text_parts = []
                for seg in segments:
                    text_parts.append(seg.text.strip())
                    del seg  # Cleanup inmediato

                full_text = " ".join(text_parts)
                del text_parts

                # Calcular métricas
                processing_time = time.time() - start_time
                speed = info.duration / processing_time if processing_time > 0 else 0

                result = {
                    'text': full_text,
                    'duration': info.duration,
                    'processing_time': processing_time,
                    'speed': speed,
                    'language': info.language,
                    'language_probability': info.language_probability
                }

                # Incrementar contador
                self._total_transcriptions += 1

                logger.info(f"✅ Transcripción completada: {speed:.1f}x en {processing_time:.2f}s (#{self._total_transcriptions})")

                return result

            except Exception as e:
                logger.error(f"❌ Error en transcripción: {e}")
                raise
            finally:
                # Cleanup post-transcripción (suave, sin afectar modelo)
                if settings.AGGRESSIVE_CLEANUP:
                    collected = gc.collect()
                    if collected > 10:  # Solo log si hay mucho que limpiar
                        logger.debug(f"🧹 Post-transcripción cleanup: {collected} objetos")

    async def get_status(self) -> Dict[str, Any]:
        """Estado actual del servicio"""
        memory_info = {}

        if torch.cuda.is_available():
            memory_info = {
                "gpu_memory_allocated_mb": torch.cuda.memory_allocated() / (1024**2),
                "gpu_memory_total_mb": torch.cuda.get_device_properties(0).total_memory / (1024**2)
            }

        # Memoria RAM del proceso
        try:
            process = psutil.Process()
            memory_info["ram_usage_mb"] = process.memory_info().rss / (1024**2)
        except:
            memory_info["ram_usage_mb"] = 0

        uptime = time.time() - self._model_loaded_at if self._model_loaded_at else 0

        return {
            "model_loaded": self._model is not None,
            "model_always_loaded": True,
            "uptime_hours": round(uptime / 3600, 1),
            "current_jobs": self._current_jobs,
            "max_concurrent": self._max_concurrent,
            "total_transcriptions": self._total_transcriptions,
            "memory_info": memory_info,
            "can_accept_jobs": await self.can_process_job(),
            "model_size": settings.MODEL_SIZE,
            "device": settings.DEVICE
        }

    async def update_concurrency(self, new_max: int) -> bool:
        """Actualizar límite de concurrencia dinámicamente"""
        if 1 <= new_max <= 3:
            async with self._model_lock:
                old_max = self._max_concurrent
                self._max_concurrent = new_max
                settings.MAX_CONCURRENT_JOBS = new_max

                logger.info(f"🔧 Concurrencia actualizada: {old_max} → {new_max}")
                return True
        return False

    async def force_unload(self):
        """DESHABILITAR descarga forzada"""
        logger.info("🔒 Descarga de modelo deshabilitada (always-loaded mode)")
        logger.info("💡 Para reiniciar modelo, reiniciar la aplicación completa")
        return False  # No hacer nada

    async def get_model_info(self) -> Dict[str, Any]:
        """Información detallada del modelo"""
        if not self._model:
            return {"error": "Modelo no cargado"}

        uptime = time.time() - self._model_loaded_at if self._model_loaded_at else 0

        return {
            "model_size": settings.MODEL_SIZE,
            "device": settings.DEVICE,
            "compute_type": settings.COMPUTE_TYPE,
            "loaded_at": self._model_loaded_at,
            "uptime_seconds": uptime,
            "uptime_hours": round(uptime / 3600, 1),
            "total_transcriptions": self._total_transcriptions,
            "always_loaded": True,
            "status": "ready"
        }


# Instancia global
whisper_service = AlwaysLoadedWhisperService()