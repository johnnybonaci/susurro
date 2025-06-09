from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TranscriptionResponse(BaseModel):
    """Respuesta al crear una transcripción"""
    job_id: str = Field(..., description="ID único del trabajo")
    status: JobStatus = Field(..., description="Estado del trabajo")
    queue_position: Optional[int] = Field(None, description="Posición en la cola")
    estimated_wait: Optional[str] = Field(None, description="Tiempo estimado de espera")
    response_time_ms: Optional[float] = Field(None, description="Tiempo de respuesta en ms")


class JobStatusResponse(BaseModel):
    """Respuesta de estado de trabajo"""
    job_id: str = Field(..., description="ID del trabajo")
    status: JobStatus = Field(..., description="Estado actual")
    filename: Optional[str] = Field(None, description="Nombre del archivo")
    created_at: Optional[float] = Field(None, description="Timestamp de creación")
    started_at: Optional[float] = Field(None, description="Timestamp de inicio")
    completed_at: Optional[float] = Field(None, description="Timestamp de finalización")
    queue_position: Optional[int] = Field(None, description="Posición en cola si está pendiente")
    message: Optional[str] = Field(None, description="Mensaje de estado")
    response_time_ms: Optional[float] = Field(None, description="Tiempo de respuesta")


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
    language_probability: Optional[float] = Field(None, description="Probabilidad del idioma")
    created_at: Optional[float] = Field(None, description="Timestamp de creación")
    completed_at: Optional[float] = Field(None, description="Timestamp de finalización")
    response_time_ms: Optional[float] = Field(None, description="Tiempo de respuesta")


class QueueStatus(BaseModel):
    """Estado de la cola"""
    pending: int = Field(..., description="Trabajos pendientes")
    processing: int = Field(..., description="Trabajos en proceso")
    completed: int = Field(..., description="Completados total")
    failed: int = Field(..., description="Fallidos total")
    total: int = Field(..., description="Total de trabajos")
    can_accept: bool = Field(..., description="Puede aceptar más trabajos")


class ServiceStatus(BaseModel):
    """Estado del servicio"""
    model_loaded: bool = Field(..., description="Modelo cargado")
    current_jobs: int = Field(..., description="Trabajos actuales")
    max_concurrent: int = Field(..., description="Máximo concurrente")
    can_accept_jobs: bool = Field(..., description="Puede aceptar trabajos")
    memory_info: dict = Field(..., description="Información de memoria")


class HealthResponse(BaseModel):
    """Respuesta health check"""
    status: str = Field(..., description="Estado general")
    redis: bool = Field(..., description="Estado Redis")
    service: bool = Field(..., description="Estado servicio")
    memory_mb: float = Field(..., description="Memoria usada en MB")