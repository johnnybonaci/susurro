import time
import torch
import threading
from typing import Optional, Tuple, Dict, Any
from faster_whisper import WhisperModel
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class WhisperService:
    """
    Servicio de transcripción con Whisper
    Basado en tu script optimizado que funciona
    """

    def __init__(self):
        self.model_pool = []
        self.model_lock = threading.Lock()
        self._initialize_models()

    def _initialize_models(self):
        """Inicializar pool de modelos (igual que tu script)"""
        logger.info(f"Inicializando {settings.MAX_CONCURRENT_JOBS} modelos Whisper...")

        # Limpiar memoria GPU antes de cargar
        torch.cuda.empty_cache()

        for i in range(settings.MAX_CONCURRENT_JOBS):
            try:
                model = self._create_model()
                self.model_pool.append(model)
                logger.info(f"Modelo {i+1}/{settings.MAX_CONCURRENT_JOBS} cargado exitosamente")
            except Exception as e:
                logger.error(f"Error cargando modelo {i+1}: {e}")
                # Si falla con GPU, intentar con CPU como en tu script
                try:
                    logger.warning("Intentando cargar modelo con CPU como respaldo...")
                    model = self._create_model(use_cpu=True)
                    self.model_pool.append(model)
                    logger.info(f"Modelo {i+1} cargado con CPU")
                except Exception as cpu_error:
                    logger.error(f"Error también con CPU: {cpu_error}")
                    break

        logger.info(f"Pool de modelos inicializado: {len(self.model_pool)} modelos disponibles")

    def _create_model(self, use_cpu: bool = False) -> WhisperModel:
        """Crear modelo con la configuración optimizada de tu script"""
        device = "cpu" if use_cpu else settings.DEVICE

        model_kwargs = {
            "device": device,
            "compute_type": settings.COMPUTE_TYPE if not use_cpu else "int8",
            "num_workers": settings.NUM_WORKERS,
            "cpu_threads": settings.CPU_THREADS
        }

        # Solo agregar device_index si usamos GPU
        if not use_cpu:
            model_kwargs["device_index"] = settings.DEVICE_INDEX

        return WhisperModel(settings.MODEL_SIZE, **model_kwargs)

    def get_model(self) -> Optional[WhisperModel]:
        """Obtener modelo del pool (thread-safe)"""
        with self.model_lock:
            return self.model_pool.pop() if self.model_pool else None

    def return_model(self, model: WhisperModel):
        """Devolver modelo al pool (thread-safe)"""
        with self.model_lock:
            self.model_pool.append(model)

    def get_available_models_count(self) -> int:
        """Número de modelos disponibles"""
        with self.model_lock:
            return len(self.model_pool)

    def transcribe_audio(self, audio_path: str) -> Dict[str, Any]:
        """
        Transcribir audio usando exactamente tu lógica optimizada
        """
        start_time = time.time()

        # Obtener modelo del pool
        model = self.get_model()
        if not model:
            raise Exception("No hay modelos disponibles en el pool")

        try:
            logger.info(f"Iniciando transcripción de: {audio_path}")

            # Transcribir con los mismos parámetros de tu script
            segments, info = model.transcribe(
                audio_path,
                beam_size=settings.BEAM_SIZE,                    # 1
                best_of=settings.BEST_OF,                        # 1
                temperature=settings.TEMPERATURE,                # 0.0
                vad_filter=settings.VAD_FILTER,                  # True
                vad_parameters={
                    "min_silence_duration_ms": settings.MIN_SILENCE_DURATION_MS,  # 300
                    "threshold": settings.VAD_THRESHOLD                           # 0.4
                },
                chunk_length=settings.CHUNK_LENGTH,              # 30
                condition_on_previous_text=settings.CONDITION_ON_PREVIOUS_TEXT,  # False
                compression_ratio_threshold=settings.COMPRESSION_RATIO_THRESHOLD,  # 2.4
                log_prob_threshold=settings.LOG_PROB_THRESHOLD,  # -1.0
                no_speech_threshold=settings.NO_SPEECH_THRESHOLD  # 0.6
            )

            # Recopilar texto exactamente como en tu script
            text_parts = []
            for seg in segments:
                text_parts.append(seg.text.strip())

            # Unir texto con espacios (como en tu script)
            full_text = " ".join(text_parts)

            # Calcular métricas
            processing_time = time.time() - start_time
            speed = info.duration / processing_time  # Velocidad como en tu script

            result = {
                'text': full_text,
                'duration': info.duration,
                'processing_time': processing_time,
                'speed': speed,
                'language': info.language,
                'language_probability': info.language_probability
            }

            logger.info(f"Transcripción completada: {speed:.1f}x tiempo real en {processing_time:.2f}s")
            return result

        except Exception as e:
            logger.error(f"Error durante transcripción: {e}")
            raise
        finally:
            # Siempre devolver el modelo al pool
            self.return_model(model)
            # Limpiar memoria GPU como en tu script
            torch.cuda.empty_cache()

    def get_gpu_info(self) -> Dict[str, Any]:
        """Información de GPU"""
        try:
            if torch.cuda.is_available():
                return {
                    "available": True,
                    "device_count": torch.cuda.device_count(),
                    "current_device": torch.cuda.current_device(),
                    "device_name": torch.cuda.get_device_name(0),
                    "memory_allocated_mb": torch.cuda.memory_allocated() / (1024**2),
                    "memory_total_mb": torch.cuda.get_device_properties(0).total_memory / (1024**2)
                }
            else:
                return {"available": False}
        except Exception as e:
            logger.error(f"Error obteniendo info GPU: {e}")
            return {"available": False, "error": str(e)}

    def cleanup_memory(self):
        """Limpiar memoria GPU"""
        try:
            torch.cuda.empty_cache()
            logger.info("Memoria GPU limpiada")
        except Exception as e:
            logger.error(f"Error limpiando memoria GPU: {e}")


# Instancia global del servicio
whisper_service = WhisperService()