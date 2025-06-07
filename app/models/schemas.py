from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TranscriptionRequest(BaseModel):
    """Modelo para solicitud de transcripción"""
    # El archivo se maneja por separado en FastAPI
    pass


class TranscriptionResponse(BaseModel):
    """Respuesta al crear una transcripción"""
    job_id: str = Field(..., description="ID único del trabajo")
    status: JobStatus = Field(..., description="Estado del trabajo")
    queue_position: Optional[int] = Field(None, description="Posición en la cola")
    estimated_wait_time: Optional[str] = Field(None, description="Tiempo estimado de espera")
    message: Optional[str] = Field(None, description="Mensaje informativo")


class JobStatusResponse(BaseModel):
    """Respuesta de estado de trabajo"""
    job_id: str = Field(..., description="ID del trabajo")
    status: JobStatus = Field(..., description="Estado actual")
    filename: Optional[str] = Field(None, description="Nombre del archivo")
    created_at: Optional[float] = Field(None, description="Timestamp de creación")
    started_at: Optional[float] = Field(None, description="Timestamp de inicio")
    queue_position: Optional[int] = Field(None, description="Posición en cola si está pendiente")
    message: Optional[str] = Field(None, description="Mensaje de estado")


class TranscriptionResult(BaseModel):
    """Resultado completo de transcripción"""
    job_id: str = Field(..., description="ID del trabajo")
    status: JobStatus = Field(..., description="Estado del trabajo")
    filename: Optional[str] = Field(None, description="Nombre del archivo original")
    text: Optional[str] = Field(None, description="Texto transcrito")
    duration: Optional[float] = Field(None, description="Duración del audio en segundos")
    processing_time: Optional[float] = Field(None, description="Tiempo de procesamiento")
    speed: Optional[float] = Field(None, description="Velocidad de procesamiento (x tiempo real)")
    language: Optional[str] = Field(None, description="Idioma detectado")
    created_at: Optional[float] = Field(None, description="Timestamp de creación")
    started_at: Optional[float] = Field(None, description="Timestamp de inicio")
    completed_at: Optional[float] = Field(None, description="Timestamp de finalización")
    error: Optional[str] = Field(None, description="Mensaje de error si falló")


class QueueStats(BaseModel):
    """Estadísticas de la cola"""
    pending: int = Field(..., description="Trabajos pendientes")
    processing: int = Field(..., description="Trabajos en proceso")
    completed_today: int = Field(..., description="Completados hoy")
    failed_today: int = Field(..., description="Fallidos hoy")
    total_jobs: int = Field(..., description="Total de trabajos")
    average_speed: Optional[float] = Field(None, description="Velocidad promedio")
    gpu_memory_mb: float = Field(..., description="Memoria GPU usada en MB")


class JobSummary(BaseModel):
    """Resumen de trabajo para listas"""
    job_id: str = Field(..., description="ID del trabajo")
    filename: Optional[str] = Field(None, description="Nombre del archivo")
    status: JobStatus = Field(..., description="Estado")
    created_at: Optional[float] = Field(None, description="Timestamp de creación")
    duration: Optional[float] = Field(None, description="Duración del audio")
    speed: Optional[float] = Field(None, description="Velocidad de procesamiento")


class JobList(BaseModel):
    """Lista de trabajos"""
    jobs: List[JobSummary] = Field(..., description="Lista de trabajos")
    total: int = Field(..., description="Total de trabajos")
    page: int = Field(..., description="Página actual")
    per_page: int = Field(..., description="Trabajos por página")


class HealthCheck(BaseModel):
    """Estado de salud del sistema"""
    status: str = Field(..., description="Estado general")
    redis_connected: bool = Field(..., description="Estado de Redis")
    models_available: int = Field(..., description="Modelos disponibles")
    gpu_available: bool = Field(..., description="GPU disponible")
    gpu_memory_mb: float = Field(..., description="Memoria GPU usada")
    uptime_seconds: float = Field(..., description="Tiempo activo en segundos")


class APIInfo(BaseModel):
    """Información de la API"""
    title: str = Field(..., description="Título de la API")
    version: str = Field(..., description="Versión")
    model_size: str = Field(..., description="Tamaño del modelo Whisper")
    max_concurrent_jobs: int = Field(..., description="Trabajos simultáneos máximos")
    allowed_formats: List[str] = Field(..., description="Formatos de archivo permitidos")
    max_file_size_mb: int = Field(..., description="Tamaño máximo de archivo en MB")


class ErrorResponse(BaseModel):
    """Respuesta de error estándar"""
    error: str = Field(..., description="Mensaje de error")
    details: Optional[str] = Field(None, description="Detalles adicionales")
    job_id: Optional[str] = Field(None, description="ID del trabajo si aplica")


class CleanupResponse(BaseModel):
    """Respuesta de limpieza"""
    message: str = Field(..., description="Mensaje de resultado")
    jobs_cleaned: int = Field(..., description="Trabajos limpiados")
    files_cleaned: int = Field(..., description="Archivos limpiados")


class AdminStats(BaseModel):
    """Estadísticas administrativas"""
    system_info: dict = Field(..., description="Información del sistema")
    queue_stats: QueueStats = Field(..., description="Estadísticas de cola")
    recent_jobs: List[JobSummary] = Field(..., description="Trabajos recientes")
    performance_metrics: dict = Field(..., description="Métricas de rendimiento")