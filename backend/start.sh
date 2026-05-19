#!/bin/sh
set -e

# Roda migrations antes de subir o app.
echo "[start.sh] alembic upgrade head"
alembic upgrade head

echo "[start.sh] starting uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
