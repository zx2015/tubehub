# === 阶段 1: 构建前端 ===
FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# === 阶段 2: 后端运行时 ===
FROM python:3.12-slim

# 系统依赖：ffmpeg + curl + ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 后端代码
COPY backend/app ./app

# 前端构建产物（Vite 默认 base=/，会被 FastAPI /static 挂载点托管）
COPY --from=frontend-builder /build/frontend/dist ./static

# 数据目录
RUN mkdir -p /app/data/videos /app/data/thumbnails /app/logs

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 启动
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
