# 07. 后端需求

> 来源：用户需求 §1, §6, §7

## 7.1 技术栈

| 项 | 选型 |
|----|------|
| 框架 | **FastAPI** 0.111+ |
| ASGI 服务器 | **Uvicorn** 0.30+ |
| Python | **3.12** |
| 数据库 | **SQLite** + **SQLAlchemy** 2.x (ORM) |
| 异步驱动 | SQLAlchemy async + `aiosqlite` |
| 下载库 | **yt-dlp** |
| 媒体处理 | **FFmpeg** (系统已装) |
| 进度推送 | **SSE** (FastAPI 原生 StreamingResponse) |
| 定时任务 | **APScheduler**（已在 venv 中预装，用于历史清理） |
| 认证 | **无认证**（内网部署，移除 SessionMiddleware） |
| 配置管理 | **pydantic-settings** + `.env` |
| 日志 | **loguru** |
| 测试 | **pytest** + **httpx** (异步测试) |

## 7.2 目录结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI 应用入口
│   ├── config.py              # pydantic-settings 配置
│   ├── database.py            # SQLAlchemy async engine
│   ├── deps.py                # 依赖注入（DB session、当前用户）
│   ├── middleware.py          # 认证、CORS、日志中间件
│   │
│   ├── models/                # SQLAlchemy 模型
│   │   ├── __init__.py
│   │   ├── video.py
│   │   ├── download_task.py
│   │   └── play_history.py
│   │
│   │ # 注意：User 模型已移除（无认证模式，见 06-auth.md）
│   │
│   ├── schemas/               # Pydantic 模型（请求/响应）
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── video.py
│   │   ├── download.py
│   │   └── history.py
│   │
│   ├── api/                   # 路由
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── videos.py
│   │   ├── downloads.py
│   │   ├── history.py
│   │   └── stream.py          # 视频流式接口
│   │
│   ├── services/              # 业务逻辑
│   │   ├── __init__.py
│   │   ├── downloader.py      # yt-dlp 封装（核心：progress_hooks、postprocessor_hooks、cancel_event）
│   │   ├── scraper.py         # 元数据刮削（extract_flat 用于歌单解析）
│   │   ├── video_service.py   # 视频文件操作（删除、批量删除）
│   │   ├── thumbnail.py       # 缩略图下载与缓存（httpx + 走代理）
│   │   ├── scheduler.py       # 异步任务调度（asyncio 循环 + Semaphore(2)）
│   │   ├── settings.py        # 系统设置（cookies / proxy 读写）
│   │   ├── history_cleaner.py # 30 天历史清理（APScheduler）
│   │   └── task_cleaner.py    # 任务记录清理（Ready 3 天 / Failed 30 天）
│   │
│   └── utils/
│       ├── __init__.py
│       ├── security.py        # 密码哈希、Session
│       └── logger.py          # loguru 配置
│
├── tests/
│   ├── test_auth.py
│   ├── test_downloads.py
│   ├── test_videos.py
│   └── conftest.py
│
├── requirements.txt
├── .env.example
└── alembic.ini                # 数据库迁移（MVP 可省略，用 create_all）
```

## 7.3 SQLite 数据库 Schema

> 来源：无认证 + 级联删除确认（见 06-auth.md, 03-library.md）
> 已删除 `users` 用户表。

```sql
-- 视频表
CREATE TABLE videos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    youtube_id      TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    uploader        TEXT,
    uploader_id     TEXT,
    source_url      TEXT NOT NULL DEFAULT '',   -- ✅ 新增：原始 YouTube 链接
    upload_date     DATE,
    duration        INTEGER,           -- 秒
    description     TEXT,
    thumbnail_path  TEXT,
    file_path       TEXT NOT NULL,
    file_size       INTEGER,
    width           INTEGER,
    height          INTEGER,
    fps             REAL,
    vcodec          TEXT,
    acodec          TEXT,
    container       TEXT,
    format_type     TEXT,              -- video only（仅视频，已裁切仅音频）
    quality_label   TEXT,
    last_position   REAL DEFAULT 0,
    last_watched_at DATETIME,
    created_at      DATETIME NOT NULL
);

CREATE INDEX idx_videos_youtube_id ON videos(youtube_id);
CREATE INDEX idx_videos_uploader ON videos(uploader);
CREATE INDEX idx_videos_created_at ON videos(created_at DESC);

-- 下载任务表
CREATE TABLE download_tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    url               TEXT NOT NULL,
    youtube_id        TEXT,
    title             TEXT,
    format_type       TEXT NOT NULL,
    quality           TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    progress          REAL DEFAULT 0,
    speed             TEXT,
    eta               TEXT,
    downloaded_bytes  INTEGER DEFAULT 0,
    total_bytes       INTEGER DEFAULT 0,
    error_message     TEXT,
    save_path         TEXT,
    retry_count       INTEGER DEFAULT 0,  -- ✅ 新增：当前已重试次数
    max_retries       INTEGER DEFAULT 3,  -- ✅ 新增：最大自动重试次数
    last_attempt_at   DATETIME,           -- ✅ 新增：最近一次尝试时间（限流退避）
    created_at        DATETIME NOT NULL,
    updated_at        DATETIME NOT NULL,
    finished_at       DATETIME
);

CREATE INDEX idx_downloads_status ON download_tasks(status);
CREATE INDEX idx_downloads_created_at ON download_tasks(created_at DESC);

-- 播放历史表
CREATE TABLE play_history (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id          INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    position          REAL DEFAULT 0,
    duration          REAL DEFAULT 0,
    progress_percent  REAL DEFAULT 0,
    completed         BOOLEAN DEFAULT 0,
    first_watched_at  DATETIME NOT NULL,
    last_watched_at   DATETIME NOT NULL,
    watch_count       INTEGER DEFAULT 1,
    UNIQUE(video_id)
);

CREATE INDEX idx_history_last_watched ON play_history(last_watched_at DESC);

-- Cookies 表（新增，用于配置并存储 yt-dlp cookie 文件）
CREATE TABLE system_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      DATETIME NOT NULL
);
```

### 7.3.1 Cookies API 与配置

- **存储机制**：上传的 `cookies.txt` 原文存储到 `system_settings` 中（key = `ytdlp_cookies`，value = 文本内容），同时写入本地 `data/cookies.txt` 供 yt-dlp 直接调用。
- **接口列表**：
  - `POST /api/settings/cookies` — 上传（文件格式 `multipart/form-data`，解析为文本存入数据库和落盘）
  - `GET /api/settings/cookies` — 获取状态（返回更新时间、是否有 Cookie，不返回原文防止泄露）
  - `DELETE /api/settings/cookies` — 清理 Cookie
- **yt-dlp 调用**：
  - 下载服务启动前，若 DB 中有 `ytdlp_cookies` 且本地无该文件，自动将内容写入本地 `data/cookies.txt`。
  - 调用 `yt_dlp.YoutubeDL` 时传入 `cookiefile="data/cookies.txt"` 参数。

### 7.3.2 全局代理配置（v2.0.0 重构 ✅）

> **架构变更（2026-07-08）**：彻底移除前端代理设置入口、后端 `ytdlp_proxy` 字段及所有代理 API。
> 代理现在通过宿主机 `.env` 文件中**系统级环境变量** `HTTP_PROXY` / `HTTPS_PROXY` 统一管理。
> 详细决策见 [00-architecture.md §ADR-04](../design/00-architecture.md)。

#### 配置位置

`backend/.env` 文件：

```bash
# === 统一全局网络代理 (用于容器内自愈、Git、Pip 及视频下载) ===
HTTP_PROXY=http://10.158.100.9:8080
HTTPS_PROXY=http://10.158.100.9:8080
```

#### 隐式捕获机制

在容器运行期间，所有网络客户端均**自动、隐式**读取环境变量中的代理：

| 客户端 | 用途 | 是否需手动传参 |
|--------|------|----------------|
| `yt-dlp` | 视频流下载 | ❌ 隐式捕获 |
| `httpx` | 缩略图下载 | ❌ 隐式捕获 |
| `git` | 容器启动拉取代码 | ✅ entrypoint.sh 显式注册 |
| `pip` | 容器启动升级依赖 | ✅ entrypoint.sh 显式注册 |

> **应用层代码绝不应**在 `yt-dlp` 的 `ydl_opts` 或 `httpx.AsyncClient()` 中手动传 `proxy` 参数！这与 v2.0.0 之前的旧实现截然不同。

#### 相关设计文档

- [00-architecture.md §ADR-04](../design/00-architecture.md) — 重构决策
- [05-settings-and-config.md](../design/05-settings-and-config.md) — 设置服务与全局代理
- [07-operations.md](../design/07-operations.md) — 容器自愈启动脚本细节

---

## 7.4 异步任务设计

### MVP 方案：FastAPI BackgroundTasks

```
优点：零依赖、足够 MVP 使用
缺点：进程崩溃则任务丢失；不支持多 worker 并发下载
```

### 生产方案：Celery + Redis（可选升级）

```
优点：分布式、可靠、支持定时任务
缺点：需额外部署 Redis
```

> ⚠️ **待澄清**：MVP 阶段是否仅用 `BackgroundTasks`？后续再升级到 Celery？
> **建议**：MVP 用 BackgroundTasks，但设计上预留抽象层 `services/scheduler.py` 便于切换。

## 7.5 配置项（.env）

```bash
# 应用
APP_NAME=TubeHub
DEBUG=false
SECRET_KEY=change-me-to-random-32-bytes

# 服务
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=http://localhost:5173

# 数据库
DATABASE_URL=sqlite+aiosqlite:///./data/tubehub.db

# 存储
DATA_DIR=./data
VIDEOS_DIR=./data/videos
THUMBNAILS_DIR=./data/thumbnails
LOGS_DIR=./logs

# 下载
MAX_CONCURRENT_DOWNLOADS=2
YTDLP_FORMAT_PREFER=mp4
YTDLP_COOKIES_FILE=          # 可选，用于绕过年龄限制

# 认证
SESSION_COOKIE_NAME=tubehub_session
SESSION_SECRET_KEY=change-me-too
SESSION_MAX_AGE=2592000      # 30 天
DEFAULT_USERNAME=admin
```

## 7.6 日志分级

| 级别 | 用途 | 输出位置 |
|------|------|----------|
| INFO | 业务事件（下载开始、任务完成、登录） | `logs/tubehub.log` + stdout |
| WARNING | 异常但可恢复（重试、降级） | `logs/tubehub.log` |
| ERROR | 失败（下载失败、API 500） | `logs/tubehub.log` + stderr |
| yt-dlp 输出 | 独立文件 | `logs/yt-dlp.log` |
| FFmpeg 输出 | 独立文件 | `logs/ffmpeg.log` |

## 7.7 CORS 配置

- 开发环境：允许 `http://localhost:5173`（Vite 默认端口）
- 生产环境：同源部署，无 CORS 问题
- 允许的 Headers：`Authorization`, `Content-Type`
- 允许的 Methods：`GET, POST, PATCH, DELETE, OPTIONS`

---

## Related

- [00-overview.md](00-overview.md) — 项目总览
- [02-downloader.md](02-downloader.md) — 下载实现
- [06-auth.md](06-auth.md) — 认证中间件
- [08-deployment.md](08-deployment.md) — 启动命令