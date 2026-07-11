#!/bin/sh
echo "[Init] TubeHub starting..."
# 工作目录设为 /app，使 data/、logs/ 等相对路径
# 对应 docker-compose 挂载的 /app/data 和 /app/logs
cd /app
export PYTHONPATH=/app/backend
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --app-dir /app/backend
