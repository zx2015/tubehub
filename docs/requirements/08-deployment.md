# 08. 部署需求

> 来源：用户需求 §9（本地 venv 运行）、§10（Docker 部署）

## Revision History

| 版本号 | 日期 | 变更说明 | 作者 |
| :--- | :--- | :--- | :--- |
| v1.0.0 | 2026-07-07 | 初始版本 | Gemini CLI |
| v2.0.0 | 2026-07-08 | **架构性升级**：(1) 引入 `entrypoint.sh` 自愈启动（git pull + pip upgrade on boot）；(2) `.env` 统一全局代理 `HTTP_PROXY`（替代前端/后端代理设置） | Gemini CLI |

## 8.1 本地开发模式（venv）

### 8.1.1 环境信息

| 项 | 值 |
|----|-----|
| venv 路径 | `/media/data/venv` |
| Python 版本 | 3.12.13 |
| 已装依赖 | fastapi 0.111.0, uvicorn 0.30.1, aiosqlite 0.22.1 |
| **待装** | **yt-dlp**（必须） |
| 外部工具 | ffmpeg 8.1.2（系统级已装） |

### 8.1.2 启动后端

```bash
# 1. 进入项目目录
cd /media/data/git/tubehub

# 2. 安装缺失依赖（首次）
/media/data/venv/bin/pip install yt-dlp sqlalchemy[asyncio] pydantic-settings \
    loguru passlib[bcrypt] python-multipart itsdangerous httpx pytest pytest-asyncio

# 3. 初始化数据目录
mkdir -p data/videos data/thumbnails logs

# 4. 复制环境变量模板并修改
cp .env.example .env
# 编辑 .env，至少修改 SECRET_KEY 与 SESSION_SECRET_KEY

# 5. 启动后端（开发模式，自动重载）
/media/data/venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 8.1.3 启动前端（开发模式）

```bash
cd frontend
npm install
npm run dev   # 默认 http://localhost:5173
```

### 8.1.4 测试

```bash
# 后端测试
/media/data/venv/bin/pytest -v

# 前端测试
cd frontend && npm test
```

### 8.1.5 已知 venv 现状

> ✅ 已装：fastapi, uvicorn, aiosqlite, sqlalchemy（基础）, alembic, anyio, httpx
> ❌ **必须补充**：
> - `yt-dlp`（核心依赖）
> - `pydantic-settings`
> - `loguru`
> - `passlib[bcrypt]`
> - `python-multipart`（FastAPI 文件上传需要）
> - `itsdangerous`（SessionMiddleware 依赖）
> - `pytest-asyncio`（异步测试）

## 8.2 Docker 部署（生产）

### 8.2.1 Dockerfile（多阶段构建）

```dockerfile
# === 阶段 1: 构建前端 ===
FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# === 阶段 2: 后端运行时 ===
FROM python:3.12-slim

# 系统依赖：ffmpeg + curl
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 后端代码
COPY backend/app ./app

# 前端构建产物
COPY --from=frontend-builder /build/frontend/dist ./static

# 数据目录（建议挂载 volume）
RUN mkdir -p /app/data/videos /app/data/thumbnails /app/logs

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 自愈启动入口（v2.0.0 增强）
COPY backend/app/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

### 8.2.2 docker-compose.yml

```yaml
version: "3.9"

services:
  tubehub:
    build:
      context: .
      network: host
      args:
        - http_proxy=${HTTP_PROXY}
        - https_proxy=${HTTPS_PROXY}
    container_name: tubehub
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      # 1. 挂载整个项目目录（含 .git）以支持自升级
      - /home/tubehub/repo:/app
      - /home/tubehub/repo/data:/app/data
      - /home/tubehub/repo/logs:/app/logs
      - /home/tubehub/repo/frontend/dist:/app/static:ro
      # 2. 自愈启动脚本
      - /home/tubehub/repo/backend/app/entrypoint.sh:/entrypoint.sh:ro
    environment:
      - SECRET_KEY=${SECRET_KEY:?required}
      - DATABASE_URL=sqlite+aiosqlite:///./data/tubehub.db
      # 3. 统一全局网络代理（Git/Pip/yt-dlp/httpx 均会自动捕获）
      - HTTP_PROXY=${HTTP_PROXY}
      - HTTPS_PROXY=${HTTPS_PROXY}
      - NO_PROXY=localhost,127.0.0.1
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 45s
```

### 8.2.3 .env（Docker 用）

```bash
# 必须：用于会话加密
SECRET_KEY=<openssl rand -hex 32>
SESSION_SECRET_KEY=<openssl rand -hex 32>

# 必须：统一全局网络代理（容器内 Git / Pip / yt-dlp / httpx 均自动捕获）
HTTP_PROXY=http://10.158.100.9:8080
HTTPS_PROXY=http://10.158.100.9:8080
```

### 8.2.4 启动命令

```bash
# 构建并启动
docker-compose up -d --build

# 查看日志
docker-compose logs -f

# 停止
docker-compose down

# 升级
docker-compose pull && docker-compose up -d --build
```

## 8.3 部署模式对比

| 维度 | 本地 venv | Docker |
|------|-----------|--------|
| 适用场景 | 开发调试 | 生产部署 |
| 启动速度 | ⚡ 快 | 🐢 需构建 |
| 隔离性 | ❌ 依赖全局环境 | ✅ 完全隔离 |
| 跨平台 | ❌ 需手动适配 | ✅ 一致 |
| 数据持久化 | 手动 | 自动（volume） |
| yt-dlp 更新 | 手动 `pip install -U yt-dlp` | 重新构建镜像 |

## 8.4 ⚠️ 待澄清

| 问题 | 默认方案 |
|------|----------|
| Docker 中 yt-dlp 如何保持最新？ | 提供 `docker-compose pull` + 重建命令；或挂载卷实现运行时更新 |
| 是否提供 CI/CD？ | ❌ MVP 不提供 |
| 是否支持反向代理（Nginx / Caddy）？ | 文档中给出示例，但不强求 |
| 多容器（拆分前端 + 后端）？ | ❌ MVP 单容器，前端静态文件由后端托管 |
| 是否需要 HTTPS？ | 部署文档中提示，但 MVP 不内置证书 |

---

## Related

- [00-overview.md](00-overview.md) — 项目总览
- [07-backend.md](07-backend.md) — 后端技术栈