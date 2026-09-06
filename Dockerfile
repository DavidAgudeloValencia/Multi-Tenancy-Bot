# syntax=docker/dockerfile:1
# ============================================================
# MultiBot — Imagen de la API (Fase 6)
# Uso: docker compose build && docker compose up
# ============================================================
FROM python:3.11-slim

# Python: sin bytecode, salida sin buffer, pip sin caché.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1) Dependencias primero (aprovecha el caché de capas de Docker).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Código de la aplicación.
COPY main.py .
COPY app ./app
COPY scripts ./scripts
COPY static ./static        # panel web de administración (/admin)
COPY knowledge ./knowledge

# Puerto del webhook dentro del contenedor.
EXPOSE 8000

# La ingesta de la base de conocimiento es un comando aparte:
#   docker compose run --rm api python -m scripts.ingest --reset
# $PORT permite a Railway inyectar el puerto; localmente usa 8000 por defecto.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
