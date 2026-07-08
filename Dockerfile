# === 阶段 1: 构建前端 ===
FROM node:20-alpine AS frontend-builder
ARG http_proxy
ARG https_proxy
ENV http_proxy=$http_proxy
ENV https_proxy=$https_proxy

WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# === 阶段 2: 运行时环境 (自愈版) ===
FROM python:3.12-slim

# 安装基本环境：ffmpeg + curl + git + ca-certificates
# 构建期无需代理 pip 依赖，转入 entrypoint 运行时代理，从而彻底杜绝构建期 502
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制 entrypoint
COPY backend/app/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 前端构建产物 (做兜底用，挂载后会被 volume 自动热覆盖)
COPY --from=frontend-builder /build/frontend/dist ./static

EXPOSE 8000

# 健康检查通过 /api/health
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s \
    CMD curl -f http://localhost:8000/api/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
