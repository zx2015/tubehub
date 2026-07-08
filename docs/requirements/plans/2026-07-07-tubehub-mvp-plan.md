# TubeHub MVP 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 TubeHub MVP 版本的单用户、内网部署、支持代理与 cookie 上传的 YouTube 下载与流媒体播放系统。

**Architecture:** 采用前后端分离模型，React 18 (Vite) 作为前端 UI 配合 video.js 8.x 播放视频与上报进度；后端使用 Python 3.12 + FastAPI 提供 RESTful API，通过全局 Semaphore(2) 实现 asyncio 协程级下载调度调度，存储层使用 SQLite。

**Tech Stack:** React 18, Vite, TS, Vanilla CSS, video.js 8, FastAPI, SQLAlchemy 2.0 (async), aiosqlite, yt-dlp, FFmpeg, httpx, loguru, APScheduler.

---

## 目录结构映射

```
tubehub/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── utils/
│   │   ├── database.py
│   │   └── main.py
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── styles/
│   │   └── main.tsx
│   └── package.json
├── data/ (gitignore)
└── logs/ (gitignore)
```

---

## 第一阶段：后端基础架构（TDD 驱动）

### Task 1: 初始化项目目录、虚拟环境与依赖

**Files:**
- Create: `backend/requirements.txt`
- Modify: `.gitignore`（已存在，检查）

- [ ] **Step 1: 写入后端 requirements.txt 依赖**

```text
fastapi==0.111.0
uvicorn==0.30.1
pydantic==2.7.4
pydantic-settings==2.3.1
sqlalchemy[asyncio]==2.0.30
aiosqlite==0.22.1
yt-dlp==2024.5.27
httpx==0.27.0
loguru==0.7.2
python-multipart==0.0.9
APScheduler==3.11.2
pytest==8.2.1
pytest-asyncio==0.23.7
```

- [ ] **Step 2: 安装依赖到本地 venv**

Run: `/media/data/venv/bin/pip install -r backend/requirements.txt`
Expected: 成功安装所有依赖且无冲突。

- [ ] **Step 3: 提交依赖**

```bash
git add backend/requirements.txt
git commit -m "chore: backend dependency lock"
```

---

### Task 2: 数据库初始化与 models 定义（TDD 验证外键）

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/database.py`
- Create: `backend/tests/test_database.py`

- [ ] **Step 1: 编写外键级联测试（TDD）**

```python
# backend/tests/test_database.py
import pytest
from sqlalchemy import select
from app.database import init_db, AsyncSessionLocal
from app.models import Video, PlayHistory

@pytest.mark.asyncio
async def test_cascade_delete_history():
    await init_db()  # 会自动创建 sqlite 内存表
    async with AsyncSessionLocal() as db:
        video = Video(youtube_id="test_id_123", title="Test Title", file_path="/mock/path")
        db.add(video)
        await db.commit()
        await db.refresh(video)
        
        history = PlayHistory(video_id=video.id, position=10.0, duration=100.0)
        db.add(history)
        await db.commit()
        
        # 删除 video
        await db.delete(video)
        await db.commit()
        
        # 验证 history 自动级联清理 (CASCADE)
        hist = (await db.execute(select(PlayHistory).where(PlayHistory.video_id == video.id))).scalar_one_or_none()
        assert hist is None
```

- [ ] **Step 2: 运行测试以验证失败**

Run: `/media/data/venv/bin/pytest backend/tests/test_database.py -v`
Expected: FAIL（"Module app not found" 或 "ImportError"）

- [ ] **Step 3: 写入 01-database-schema 中的完整 models 和 database 代码**

- 写入 `backend/app/models/__init__.py` (SQLAlchemy 完整类)
- 写入 `backend/app/database.py` (包含 `PRAGMA foreign_keys = ON;`)

- [ ] **Step 4: 运行测试验证通过**

Run: `/media/data/venv/bin/pytest backend/tests/test_database.py -v`
Expected: PASS（SQLite CASCADE 自动生效）

- [ ] **Step 5: 提交数据库核心代码**

```bash
git add backend/app/models/__init__.py backend/app/database.py backend/tests/test_database.py
git commit -m "feat: add models and database cascade test"
```

---

## 第二阶段：核心服务与 yt-dlp 深度集成

### Task 3: 编写 settings 存储服务与代理/cookie

**Files:**
- Create: `backend/app/services/settings.py`
- Create: `backend/tests/test_settings.py`

- [ ] **Step 1: 编写代理测试与 cookies 文件读写测试**

```python
# backend/tests/test_settings.py
import pytest
import os
from app.services.settings import SettingsService, COOKIES_FILE_PATH

@pytest.mark.asyncio
async def test_cookies_upload():
    if os.path.exists(COOKIES_FILE_PATH):
        os.remove(COOKIES_FILE_PATH)
    await SettingsService.set_cookies("mock_cookies_content")
    assert os.path.exists(COOKIES_FILE_PATH)
    status = await SettingsService.get_cookies_status()
    assert status["has_cookie"] is True
```

- [ ] **Step 2: 运行测试以验证失败**

Run: `/media/data/venv/bin/pytest backend/tests/test_settings.py -v`
Expected: FAIL (SettingsService 未实现)

- [ ] **Step 3: 编写 `backend/app/services/settings.py` 的实现**

- 包含 05-settings-and-config.md 中的 `get_proxy`、`set_proxy`、`get_cookies_status`、`set_cookies`、`clear_cookies`

- [ ] **Step 4: 运行测试验证通过**

Run: `/media/data/venv/bin/pytest backend/tests/test_settings.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/settings.py backend/tests/test_settings.py
git commit -m "feat: add settings service and cookies sync"
```

---

### Task 4: asyncio 调度器与下载器核心

**Files:**
- Create: `backend/app/services/scheduler.py`
- Create: `backend/app/services/downloader.py`
- Create: `backend/tests/test_scheduler.py`

- [ ] **Step 1: 编写 TDD 异步并发上限(2) 测试**

```python
# backend/tests/test_scheduler.py
import pytest
import asyncio
from app.services.scheduler import download_semaphore

@pytest.mark.asyncio
async def test_concurrency_slots():
    assert download_semaphore._value == 2
```

- [ ] **Step 2: 运行测试以验证失败**

Run: `/media/data/venv/bin/pytest backend/tests/test_scheduler.py -v`
Expected: FAIL

- [ ] **Step 3: 写入调度器实现**

- 写入 `backend/app/services/scheduler.py` (asyncio Semaphore(2) 控制，lifespan 钩子拉起)
- 写入 `backend/app/services/downloader.py` (CancellableYDL、progress_hooks 协作取消、Merger 合并状态更新、自动重试 3 次，详见设计 03)

- [ ] **Step 4: 运行测试验证通过**

Run: `/media/data/venv/bin/pytest backend/tests/test_scheduler.py -v`
Expected: PASS

- [ ] **Step 5: 提交调度核心**

```bash
git add backend/app/services/scheduler.py backend/app/services/downloader.py backend/tests/test_scheduler.py
git commit -m "feat: add asyncio Semaphore scheduler and downloader"
```

---

### Task 5: 缩略图下载服务与代理联动

**Files:**
- Create: `backend/app/services/thumbnail.py`
- Create: `backend/tests/test_thumbnail.py`

- [ ] **Step 1: 编写缩略图降级链测试**

```python
# backend/tests/test_thumbnail.py
import pytest
import os
from app.services.thumbnail import download_thumbnail

@pytest.mark.asyncio
async def test_thumbnail_download_fallback():
    # 测试拉取无效视频 ID 触发降级并返回占位图
    path = await download_thumbnail("invalid_id_xxxx")
    assert path == "static/placeholder-thumbnail.jpg"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `/media/data/venv/bin/pytest backend/tests/test_thumbnail.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/app/services/thumbnail.py`**

- 使用 httpx 通过用户代理下载，优先 `hqdefault`。降级链：`hqdefault → mqdefault → default → 占位图`。保存至 `data/thumbnails/{video_id}.jpg`。

- [ ] **Step 4: 运行测试验证通过**

Run: `/media/data/venv/bin/pytest backend/tests/test_thumbnail.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/thumbnail.py backend/tests/test_thumbnail.py
git commit -m "feat: add proxy-aware thumbnail downloader with fallback"
```

---

## 第三阶段：RESTful API 契约落地

### Task 6: 编写 FastAPI APP 与路由、SSE 推送

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/api/downloads.py`
- Create: `backend/app/api/videos.py`
- Create: `backend/app/api/health.py`
- Create: `backend/tests/test_api.py`

- [ ] **Step 1: 编写 API 接口测试（TDD）**

```python
# backend/tests/test_api.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_health_api():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/api/health")
    assert r.status_code == 200
    assert "status" in r.json()
```

- [ ] **Step 2: 运行测试验证失败**

Run: `/media/data/venv/bin/pytest backend/tests/test_api.py -v`
Expected: FAIL

- [ ] **Step 3: 落实 Pydantic schemas 与 FastAPI 路由代码**

- 写入 `backend/app/schemas/` 包含 `download.py`、`video.py`、`settings.py`。
- 写入 `backend/app/main.py` (含 lifespan，全局错误拦截)。
- 写入各路由，确保 API 返回符合 02-api-design.md 中的字段与状态码。

- [ ] **Step 4: 运行测试验证通过**

Run: `/media/data/venv/bin/pytest backend/tests/test_api.py -v`
Expected: PASS

- [ ] **Step 5: 提交全套 API 路由**

```bash
git add backend/app/main.py backend/app/api/ backend/app/schemas/ backend/tests/test_api.py
git commit -m "feat: add full FastAPI routing, schemas and health API"
```

---

## 第四阶段：前端组件与 Web 播放器（React）

### Task 7: 初始化前端（React 18 + Vite + TS）与 video.js 集成

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/src/components/VideoJSPlayer.tsx`

- [ ] **Step 1: 写入前端 package.json**

- 写入设计 00 指定的前端包（React, Vite, video.js 8, lucide-react 等）。

- [ ] **Step 2: 安装前端依赖并启动开发服务器验证环境**

Run: `cd frontend && npm install`
Expected: 成功拉取并安装 node_modules。

- [ ] **Step 3: 写入 `VideoJSPlayer.tsx` 核心包装层**

- 完整复刻设计 04 中的 video.js 包装代码，包含 timeupdate 每 5 秒 PATCH 上报进度，以及 beforeunload 利用 `navigator.sendBeacon` 最后的兜底上报。

- [ ] **Step 4: 编写最简测试或编译检查**

Run: `cd frontend && npm run build` (或 tsc 编译检查)
Expected: 编译通过且无 TS 错误。

- [ ] **Step 5: 提交前端基础与播放器包装**

```bash
git add frontend/package.json frontend/src/components/VideoJSPlayer.tsx
git commit -m "feat: frontend bootstrap and videojs player integration"
```

---

### Task 8: 编写前端 4 个页面（Vanilla CSS 样式扁平网格）

**Files:**
- Create: `frontend/src/components/VideoLibrary.tsx`
- Create: `frontend/src/components/DownloadTasks.tsx`
- Create: `frontend/src/components/Settings.tsx`
- Create: `frontend/src/styles/`（Vanilla CSS）

- [ ] **Step 1: 编写核心页面组件**

- `<VideoLibrary />`：网格卡片、[🗑] 单删按钮、Checkbox 批量选择、顶部批量删除确认。
- `<DownloadTasks />`：进度条、SSE 实时刷新（使用 useSSE hook）、Failed 任务重试。
- `<Settings />`：Cookie 文本上传、代理 IP/端口/用户名/密码 + 连通性测试。

- [ ] **Step 2: 编写样式**

- 使用 CSS 变量 (theme.css) 规范深色/浅色配色。
- 视频库卡片使用 flex/grid 响应式：手机 2 列，平板 3 列，桌面 5 列。

- [ ] **Step 3: 编译验证**

Run: `cd frontend && npm run build`
Expected: 编译零报错。

- [ ] **Step 4: 提交前端全套页面**

```bash
git add frontend/src/
git commit -m "feat: complete React pages for library, downloads, and settings"
```

---

## 第五阶段：部署、测试与运维封顶

### Task 9: 编写 Dockerfile 与 docker-compose.yml 封顶

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: 编写 Dockerfile（多阶段构建）**

- 阶段 1：构建前端 React 静态产物到 `static/`。
- 阶段 2：后端 Python 运行时，安装 ffmpeg、curl、ca-certificates。

- [ ] **Step 2: 编写 docker-compose.yml**

- 完整映射 `data/` 和 `logs/`，利用 HEALTHCHECK 探测 `/api/health` 确保容器高可用。

- [ ] **Step 3: 运行完整后端 Pytest 测试，确保整体逻辑无 Regressions**

Run: `/media/data/venv/bin/pytest backend/tests/ -v`
Expected: 100% PASS

- [ ] **Step 4: 提交**

```bash
git add Dockerfile docker-compose.yml
git commit -m "deploy: add production dockerfile and docker-compose.yml"
```

---

## Related

- [`../design/`](../design/) — 设计文档
- [`../requirements/`](../requirements/) — 需求基线
- [`../../GEMINI.md`](../../GEMINI.md) — 项目指令准则