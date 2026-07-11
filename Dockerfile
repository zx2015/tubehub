# ============================================================
# Stage 1: 前端构建（仅 package*.json 变化时才重跑 npm ci）
# ============================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /build

# 单独 COPY 依赖描述文件，利用 Docker 层缓存
# 只要 package.json / package-lock.json 未变，此层完全命中缓存
COPY frontend/package*.json ./
RUN npm ci --prefer-offline

# 再 COPY 源码并构建
COPY frontend/ ./
RUN npm run build

# ============================================================
# Stage 2: 后端运行时
# ============================================================
FROM python:3.12-slim

ARG HTTP_PROXY
ARG HTTPS_PROXY

# 使用国内镜像源，安装系统依赖（含 deno 用于 yt-dlp JS 运行时）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

# 安装 deno（yt-dlp 2026.07+ 需要 JS 运行时来处理受限视频）
RUN curl ${HTTP_PROXY:+-x $HTTP_PROXY} -fsSL https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip \
        -o /tmp/deno.zip \
    && unzip /tmp/deno.zip -d /usr/local/bin \
    && rm /tmp/deno.zip \
    && deno --version

WORKDIR /app

# 单独 COPY requirements.txt，依赖不变时完全命中缓存
COPY backend/requirements.txt ./backend/

# pip 缓存由 BuildKit 的 --mount=type=cache 管理；
# 代理通过 ARG 注入，仅构建阶段生效，不污染运行时镜像
RUN pip install \
    ${HTTP_PROXY:+--proxy $HTTP_PROXY} \
    -r backend/requirements.txt

# 后端源码（变更最频繁，放最后）
COPY backend/ ./backend/

# 前端构建产物
COPY --from=frontend-builder /build/dist /app/backend/static

# 启动脚本
RUN chmod +x /app/backend/app/entrypoint.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

ENTRYPOINT ["/app/backend/app/entrypoint.sh"]
