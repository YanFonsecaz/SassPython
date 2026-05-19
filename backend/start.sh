#!/bin/bash
set -e

echo "[start.sh] alembic upgrade head"
alembic upgrade head

# No tier free do Render nao da pra ter Background Worker separado,
# entao subimos o ARQ worker dentro do mesmo container do web service.
echo "[start.sh] starting arq worker in background"
python -m arq app.worker.WorkerSettings &
WORKER_PID=$!

# Se o worker morrer, derruba o container junto pra Render reiniciar.
trap "kill -TERM $WORKER_PID 2>/dev/null; exit 1" TERM INT

echo "[start.sh] starting uvicorn"
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
