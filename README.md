# Whisper Transcription API

## Instalación Rápida

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Configurar entorno
cp .env.example .env

# 3. Ejecutar
python run.py
```

## Prueba Rápida

```bash
# Probar endpoint básico
curl http://localhost:8000/

# Probar transcripción
curl -X POST "http://localhost:8000/transcribe" \
     -F "file=@tu_audio.mp3"
```

## Endpoints Disponibles

- `GET /` - Info básica
- `GET /health` - Estado del sistema
- `POST /transcribe` - Transcribir archivo
- `GET /docs` - Documentación interactiva

## Estructura Creada

```
whisper-api/
├── app/
│   ├── main.py           # App principal
│   ├── config.py         # Configuración
│   ├── models/schemas.py # Modelos Pydantic
│   ├── core/whisper_service.py  # lógica optimizada
│   └── utils/logger.py   # Sistema de logs
├── temp_uploads/         # Archivos temporales
├── requirements.txt      # Dependencias
├── .env.example         # Configuración ejemplo
└── run.py               # Script de inicio
```
