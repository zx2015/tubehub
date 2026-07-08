#!/bin/sh
set -e

# ===========================================================================
# TubeHub 容器运行时自愈升级引导脚本 (entrypoint.sh)
# ===========================================================================

echo "=== [Startup] Initializing Self-Healing sequence ==="

# 1. 检测全局代理，全自动注入 git
if [ -n "$HTTP_PROXY" ]; then
    echo "=== [Proxy] Global Proxy detected: $HTTP_PROXY ==="
    git config --global http.proxy "$HTTP_PROXY"
    git config --global https.proxy "$HTTP_PROXY"
fi

# 避开 Git 安全目录所有权校验 (Docker volume 挂载常见权限问题)
git config --global --add safe.directory /app

# 2. 丢弃本地修改并拉取最新 GitHub 代码
if [ -d ".git" ]; then
    echo "=== [Self-Healing] Syncing codebase with GitHub main ==="
    # 强制废弃由于本地卷调试引起的 dirty working tree，保证与线上同步
    git reset --hard
    git fetch --all
    # 自适应拉取 main 或 master 分支
    git pull origin main || git pull origin master || echo "[WARN] Git pull failed, starting with local cache"
else
    echo "[WARN] No .git directory found. Skipping code sync"
fi

# 3. 升级 pip 并热升级 requirements.txt
if [ -f "backend/requirements.txt" ]; then
    echo "=== [Self-Healing] Upgrading pip & installing dependencies ==="
    pip install --no-cache-dir --upgrade pip
    pip install --no-cache-dir --upgrade -r backend/requirements.txt
else
    echo "[WARN] No requirements.txt found. Skipping dependency sync"
fi

# 4. 挂载完成后，启动 FastAPI Uvicorn ASGI 服务
echo "=== [Startup] Launching TubeHub Backend Main Server ==="
cd backend
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
