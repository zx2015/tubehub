# 07. 部署与运维设计

> 涵盖：启动顺序、健康检查、日志格式、备份/恢复、Docker Compose 启动流程。

## Revision History

| 版本号 | 日期 | 变更说明 | 作者 |
| :--- | :--- | :--- | :--- |
| v1.0.0 | 2026-07-07 | 初始版本 | Gemini CLI |
| v2.0.0 | 2026-07-08 | 新增"容器自愈启动入口"机制（git pull + pip upgrade on boot） | Gemini CLI |
| v2.0.1 | 2026-07-10 | 按当前代码修正 entrypoint 与部署行为说明 | Copilot |

## 7.1 启动顺序

### 7.1.0 容器启动入口（当前实现）

`backend/app/entrypoint.sh` 是 Docker 容器的统一启动入口。

**当前能力**：
1. 切换目录到 `/app/backend`
2. 设置 `PYTHONPATH=/app/backend`
3. 以 `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1` 启动

**执行时序**：
```mermaid
sequenceDiagram
    autonumber
    participant DC as Docker Daemon
    participant E as entrypoint.sh
    participant UV as Uvicorn

    DC->>E: docker compose up (启动容器)
    E->>E: cd /app/backend
    E->>E: export PYTHONPATH=/app/backend
    E->>UV: exec uvicorn app.main:app --workers 1
    UV-->>DC: 监听 0.0.0.0:8000
```

**操作员日常工作流**：
```bash
# 本地有代码更新
git add -A && git commit -m "..." && git push origin main

# 远程仅需重启容器即可一键升级
ssh tcagent-z15 "cd /home/tubehub/repo && docker compose restart tubehub"
```

代码更新与依赖升级需通过重新构建镜像完成，启动脚本本身不执行 git/pip 自愈动作。

### 7.1.1 本地 venv 启动

```bash
# 1. 安装依赖
/media/data/venv/bin/pip install -r backend/requirements.txt
cd frontend && npm install

# 2. 初始化数据目录
mkdir -p data/videos data/thumbnails logs

# 3. 创建 .env（如不存在）
cp .env.example .env

# 4. 启动后端（开发模式）
cd /media/data/git/tubehub
/media/data/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 5. 启动前端（另一终端）
cd frontend && npm run dev
```

### 7.1.2 启动时序

```mermaid
sequenceDiagram
    autonumber
    participant U as uvicorn
    participant L as FastAPI lifespan
    participant DB as SQLite
    participant FS as 文件系统
    participant S as 调度器
    participant C as 清理器

    U->>L: 启动 lifespan
    L->>DB: init_db() 建表 + 启用外键
    L->>FS: 检查 data/ cookies.txt
    alt 存在 system_settings.ytdlp_cookies
        L->>FS: 恢复 data/cookies.txt
    end
    L->>S: 创建 asyncio.create_task(scheduler_loop)
    L->>C: 创建 asyncio.create_task(cleaner_loop)
    L-->>U: 应用就绪
```

## 7.2 健康检查

### 7.2.1 API 端点

```python
# backend/app/api/health.py
from fastapi import APIRouter
from sqlalchemy import text
from ..database import AsyncSessionLocal

router = APIRouter()


@router.get("/api/health")
async def health():
    checks = {}
    
    # 1. 数据库可达
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"fail: {e}"
    
    # 2. FFmpeg 可用
    import shutil
    checks["ffmpeg"] = "ok" if shutil.which("ffmpeg") else "missing"
    
    # 3. 磁盘空间
    import shutil
    usage = shutil.disk_usage("data/")
    checks["disk_free_gb"] = round(usage.free / 1024**3, 2)
    
    status = "ok" if all(
        v == "ok" or (isinstance(v, (int, float)) and v > 5)
        for v in checks.values()
    ) else "degraded"
    
    return {"status": status, **checks}
```

### 7.2.2 Docker 健康检查

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s \
    CMD curl -f http://localhost:8000/api/health || exit 1
```

## 7.3 日志规范

- 路径：`./logs/`
- 滚动：单文件 20MB，最多保留 14 天，启用 gzip 压缩
- 三个独立日志：
  - `tubehub.log`：应用业务日志（DEBUG）
  - `ytdlp.log`：yt-dlp 引擎日志（INFO）
  - `ffmpeg.log`：FFmpeg 输出（INFO）

## 7.4 备份与恢复

### 7.4.1 备份范围

```bash
# 完整备份（推荐每次升级前执行）
tar -czf tubehub-backup-$(date +%Y%m%d).tar.gz \
    data/tubehub.db \
    data/thumbnails/ \
    data/videos/ \
    logs/
```

### 7.4.2 备份策略

| 级别 | 频率 | 保留 | 工具 |
|------|------|------|------|
| 日常备份 | 每周日 02:00 | 保留 4 周 | cron + tar |
| 升级前 | 手动 | 永久 | 手动执行 |

### 7.4.3 恢复流程

```bash
# 1. 停止服务
docker-compose down

# 2. 解压备份
tar -xzf tubehub-backup-20260707.tar.gz

# 3. 重启服务
docker-compose up -d
```

## 7.5 Docker Compose

> 文件位置：`docker-compose.yml` + `Dockerfile`

```yaml
version: "3.9"

services:
  tubehub:
    build: .
    container_name: tubehub
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - SECRET_KEY=${SECRET_KEY:?required}
      - DATABASE_URL=sqlite+aiosqlite:///./data/tubehub.db
      - DATA_DIR=/app/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

## 7.6 升级流程

```bash
# 1. 备份
make backup  # 或手动执行 tar

# 2. 拉取最新代码
git pull

# 3. 更新依赖
docker-compose build --pull

# 4. 滚动重启
docker-compose up -d

# 5. 验证健康
curl http://localhost:8000/api/health
```

## 7.7 性能监控（MVP 不集成 Sentry）

- 通过 `logs/tubehub.log` 监控错误率
- 通过 `/api/health` 监控磁盘空间
- 手动检查任务清理是否正常工作

---

## Related

- [00-architecture.md](00-architecture.md) — 整体架构
- [06-error-handling.md](06-error-handling.md) — 错误处理