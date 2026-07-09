#!/bin/sh
echo "[Init] TubeHub starting..."
cd /app/backend
export PYTHONPATH=/app/backend
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
