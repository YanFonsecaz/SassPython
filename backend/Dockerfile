# syntax=docker/dockerfile:1.6

# =========================================
# Stage 1: build frontend Next.js (export estatico)
# =========================================
FROM node:20-slim AS frontend-builder
WORKDIR /fe

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# =========================================
# Stage 2: backend Python
# =========================================
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/ /app/
RUN pip install --no-cache-dir .

# Coloca em /frontend/out porque o backend usa
# Path(__file__).resolve().parent.parent.parent/"frontend"/"out"
# que dentro do container resolve para `/frontend/out`.
COPY --from=frontend-builder /fe/out /frontend/out

RUN chmod +x /app/start.sh && mkdir -p /app/uploads/imagens

EXPOSE 8000

# Default = web service. Worker sobrescreve via CMD no Render.
CMD ["/app/start.sh"]
