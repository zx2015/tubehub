# 03. yt-dlp 集成设计

> 核心服务层设计：调度器 + 下载器 + 取消 + 重试。基于需求 02 §2.2 ~ 2.9 + .learnings/yt-dlp-integration.md

## Revision History

| 版本号 | 日期 | 变更说明 | 作者 |
| :--- | :--- | :--- | :--- |
| v1.0.0 | 2026-07-07 | 初始集成设计 | Gemini CLI |
| v1.1.0 | 2026-07-07 | 追加动态格式、cookies、代理配置与端到端下载流程说明 | Gemini CLI |

---

## 3.0 端到端下载处理流程

在 TubeHub 中，用户点击 `[＋ 新增下载]` 到视频成功入库供 Web 播放器播放，共跨越 6 个核心阶段。其整体时序与数据流设计如下：

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户
    participant FE as React 前端
    participant BE as FastAPI 后端
    participant Sched as 调度器 (asyncio)
    participant YTDL as yt-dlp 核心
    participant DB as SQLite 数据库
    participant FS as HDD 存储层
    participant Thumb as thumbnail.py

    User->>FE: 点击 [+ 新增下载] 输入 URL
    FE->>BE: POST /api/downloads/check { url }
    BE->>YTDL: extract_info(url, download=False)
    YTDL-->>BE: 返回 formats / video_id / title
    BE->>DB: 检查库中是否已有此视频 id
    alt 视频已存在 (Conflict)
        BE-->>FE: 返回 conflict=true + existing_video
        FE->>User: 弹出覆盖确认弹窗
        User->>FE: 点击 "确认覆盖"
        FE->>BE: POST /api/downloads { url, overwrite=true }
    else 视频不存在 (正常流)
        BE-->>FE: 返回 conflict=false
        FE->>BE: POST /api/downloads { url, overwrite=false }
    end
    BE->>DB: 写入 download_tasks (状态: queued)
    BE-->>FE: 返回 201 Created (前端刷新为 queued)
    
    Note over Sched,YTDL: 调度环每 1 秒轮询 queued 任务

    loop 异步下载调度环
        Sched->>DB: 查询最早的 queued 任务
        DB-->>Sched: 返回任务列表 (限制并发≤2)
        Sched->>BE: 状态更新: queued -> downloading
        Sched->>YTDL: run_download_worker(task_id, cancel_event)
        activate YTDL
        YTDL->>YTDL: 1) extract_info(download=False) 获取格式列表
        YTDL->>YTDL: 2) select_dynamic_format 挑出最佳 format_id
        YTDL->>DB: 自愈更新视频 Title 字段
        YTDL->>YTDL: 3) extract_info(download=True) 开始真正流下载
        loop 每一分片下载中
            YTDL->>DB: progress_callback 更新 progress/speed/eta
            FE->>BE: GET /api/downloads/{id}/stream (SSE 订阅)
            BE-->>FE: 持续推送 event: progress (1s 间隔)
        end
        YTDL->>YTDL: postprocessor_callback (FFmpeg 合并完成)
        YTDL->>DB: 状态更新: downloading -> merging -> ready
        YTDL->>Thumb: download_thumbnail(youtube_id) 走代理
        Thumb->>FS: 下载封面图到 data/thumbnails/
        YTDL->>DB: 写入 videos 主表 (建立 play_history 级联)
        YTDL->>FS: 视频写入 HDD data/videos/{uploader}/
        deactivate YTDL
    end
```

### 3.0.1 六阶段详解

#### 阶段 ① — 用户发起（前端 UI）
- **触发**：用户在「下载任务」页面右上角点击 `[＋ 新增下载]`（已收纳，视频库主页仅作纯净展示）。
- **参数**：包含 `url`、`quality`（画质，如 `720p`）。

#### 阶段 ② — 前置 check（防重机制）
- **API**：`POST /api/downloads/check`。
- **机制**：后端仅拉取 formats 元信息，探测是否与库中已有视频 ID 冲突。若冲突，前端会拉起覆盖确认对话框，用户点击确认后会携带 `overwrite=true` 执行下载。

#### 阶段 ③ — 任务创建（写入数据库）
- **API**：`POST /api/downloads`。
- **歌单处理**：若是歌单链接，后台会自动 `extract_flat` 解析并将所有子视频扁平地写入 `download_tasks` 表，所有任务状态初置为 `queued`。

#### 阶段 ④ — 调度器拾取（asyncio 信号量）
- **模块**：`services/scheduler.py` 中的 `scheduler_loop()`。
- **机制**：通过 `asyncio.Semaphore(2)` 全局控制并发。调度协程每秒巡检，将 queued 推进到pending，并在子线程中拉起 worker 进程不阻塞应用主循环。

#### 阶段 ⑤ — Worker 执行（动态格式优选）
- **模块**：`services/downloader.py`。
- **动态选格式**：
  - 先用 `extract_info(download=False)` 获取该视频在 YouTube 的格式数组。
  - 动态过滤出当前高度限制下（例如 `<=720px`）的最佳视频轨 `best_v` 与最佳音频轨 `best_a`。
  - 拼装格式为 `"399+251"` (即 `bestvideo_id+bestaudio_id/best`)，彻底规避因静态映射导致老视频缺少画质而下载报错的崩溃。
  - **PO-Token 绕过**：强制配置 `player_client = ["tv", "android", "web"]`（优先 TV 终端）配合您上传的 Netscape Cookies。
- **落盘自愈**：音视频下载完成后，调用 FFmpeg 自动合并为 MP4，写入视频表并自愈视频 Title。
- **缩略图**：调用 `download_thumbnail` 通过代理下载。

#### 阶段 ⑥ — 前端 SSE 实时刷新
- **接口**：`GET /api/downloads/{id}/stream`。
- **机制**：FastAPI `StreamingResponse` 每隔 1s 将进度帧推送至前端 useSSE 钩子，渲染一维单行流进度条，直至 ready/failed/cancelled 时连接优雅断开。

---

## 3.1 文件清单

| 文件 | 职责 |
|------|------|
| `services/scheduler.py` | asyncio 循环 + Semaphore(2) + cancel_events 池 |
| `services/downloader.py` | yt-dlp 封装：opts 构造、钩子、取消、重试 |
| `services/scraper.py` | 元数据提取（单视频 + 歌单） |
| `services/thumbnail.py` | httpx 走代理下载缩略图 |
| `services/task_cleaner.py` | 每日清理 Ready 3 天 / Failed 30 天 |

## 3.2 调度器设计（scheduler.py）

### 3.2.1 核心数据结构

```python
# 全局信号量：限制同时 downloading 的任务数
download_semaphore = asyncio.Semaphore(2)

# 取消事件池：worker 协程可通过它优雅终止
cancel_events: dict[int, asyncio.Event] = {}
```

### 3.2.2 主循环

```python
async def scheduler_loop():
    """每 1 秒检查一次 queued 任务，拾取最多 N 个推进"""
    while True:
        try:
            slots = download_semaphore._value  # 剩余槽位
            if slots <= 0:
                await asyncio.sleep(1)
                continue

            async with AsyncSessionLocal() as db:
                # 按 FIFO 取最早 queued 的任务
                stmt = (select(DownloadTask)
                        .where(DownloadTask.status == "queued")
                        .order_by(DownloadTask.created_at.asc())
                        .limit(slots))
                tasks = (await db.execute(stmt)).scalars().all()

                for task in tasks:
                    task.status = "pending"
                    await db.commit()
                    # 启动 worker 协程（不阻塞调度循环）
                    asyncio.create_task(run_download_worker(task.id))

        except Exception as e:
            logger.exception(f"scheduler_loop error: {e}")
        await asyncio.sleep(1)
```

### 3.2.3 FastAPI 启动钩子

```python
# app/main.py
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    scheduler_task = asyncio.create_task(scheduler_loop())
    cleaner_task = asyncio.create_task(task_cleaner.schedule())
    yield
    # 关闭
    scheduler_task.cancel()
    cleaner_task.cancel()
```

## 3.3 下载器设计（downloader.py）

### 3.3.1 构造 yt-dlp 选项

```python
def build_ydl_opts(
    task: DownloadTask,
    proxy_url: str | None,
    cookies_path: str | None,
    output_dir: str,
) -> dict:
    """根据任务配置构造 yt-dlp 选项"""
    quality_map = {
        "best":   "bestvideo+bestaudio/best",
        "1080p":  "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p":   "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p":   "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "worst":  "worstvideo+worstaudio/worst",
    }

    return {
        "format": quality_map[task.quality],
        "merge_output_format": "mp4",
        "outtmpl": f"{output_dir}/%(uploader)s/%(title)s [%(id)s].%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "writethumbnail": False,                 # 缩略图由后端单独下载（走代理）

        "proxy": proxy_url,
        "cookiefile": cookies_path,

        # 钩子：进度 + 后处理
        "progress_hooks": [lambda d: progress_callback(d, task.id)],
        "postprocessor_hooks": [lambda d: postprocessor_callback(d, task.id)],
    }
```

### 3.3.2 进度回调

```python
def progress_callback(d: dict, task_id: int):
    """progress_hooks 回调：更新 DB + 通知 SSE"""
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimated") or 0
        downloaded = d.get("downloaded_bytes", 0)
        percent = (downloaded / total * 100) if total else 0.0
        speed = d.get("_speed_str", "0 B/s")
        eta = d.get("_eta_str", "00:00")

        # 注意：hook 在子线程中运行，必须用 call_soon_threadsafe 调度到事件循环
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(
            asyncio.create_task,
            update_task_progress(task_id, "downloading", percent, speed, eta, downloaded, total)
        )

    elif d["status"] == "finished":
        # 单个文件下载完成；合并阶段由 postprocessor_hook 接管
        pass
```

### 3.3.3 后处理回调

```python
def postprocessor_callback(d: dict, task_id: int):
    pp = d.get("postprocessor")
    if d["status"] == "started":
        # 进入合并阶段
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(
            asyncio.create_task,
            update_task_status(task_id, "merging")
        )
    elif d["status"] == "finished" and pp == "Merger":
        # 合并完成 → 立即入库
        filepath = d.get("info_dict", {}).get("filepath")
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(
            asyncio.create_task,
            on_download_finished(task_id, filepath)
        )
```

### 3.3.4 取消与重试

```python
class CancellableYDL(yt_dlp.YoutubeDL):
    """继承 YoutubeDL，子类化 _progress_hook 注入取消逻辑"""
    def __init__(self, params: dict, cancel_event: asyncio.Event, **kw):
        super().__init__(params, **kw)
        self._cancel = cancel_event

    def _progress_hook(self, d: dict):
        if self._cancel.is_set():
            raise yt_dlp.utils.DownloadCancelled()
        return super()._progress_hook(d)


async def run_download_worker(task_id: int):
    cancel_event = asyncio.Event()
    cancel_events[task_id] = cancel_event

    async with download_semaphore:
        try:
            task = await get_task(task_id)
            ydl_opts = build_ydl_opts(task, proxy_url, cookies_path, DATA_DIR)

            loop = asyncio.get_running_loop()
            def _sync_download():
                with CancellableYDL(ydl_opts, cancel_event) as ydl:
                    return ydl.extract_info(task.url, download=True)

            info = await loop.run_in_executor(None, _sync_download)
            await on_download_finished(task_id, info)

        except yt_dlp.utils.DownloadCancelled:
            await mark_task_cancelled(task_id)
        except Exception as e:
            await handle_download_failure(task_id, str(e))
        finally:
            cancel_events.pop(task_id, None)


async def handle_download_failure(task_id: int, error: str):
    """失败处理：自动重试 3 次（详见需求 02 §2.8）"""
    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        task.retry_count += 1
        task.error_message = error[:500]
        task.last_attempt_at = datetime.utcnow()

        if task.retry_count <= task.max_retries:
            # 自动重试
            task.status = "queued"
            # 退避：第 1 次立即，第 2 次 30s，第 3 次 2min
            backoff = RETRY_BACKOFFS[task.retry_count]
            task.last_attempt_at = datetime.utcnow() + timedelta(seconds=backoff)
            logger.warning(f"Task {task_id} auto-retry ({task.retry_count}/{task.max_retries})")
        else:
            task.status = "failed"
            task.finished_at = datetime.utcnow()
            logger.error(f"Task {task_id} final fail")
        await db.commit()
```

## 3.4 缩略图下载（thumbnail.py）

```python
async def download_thumbnail(video_id: str, proxy_url: str | None) -> str | None:
    """按 hqdefault → mqdefault → default 降级链下载缩略图"""
    save_path = os.path.join(THUMBNAIL_DIR, f"{video_id}.jpg")
    if os.path.exists(save_path):
        return save_path

    for size in ["hqdefault", "mqdefault", "default"]:
        url = f"https://img.youtube.com/vi/{video_id}/{size}.jpg"
        try:
            async with httpx.AsyncClient(proxy=proxy_url, timeout=10.0) as client:
                r = await client.get(url)
                # YouTube 占位图通常 < 1KB，过滤掉
                if r.status_code == 200 and len(r.content) > 1024:
                    with open(save_path, "wb") as f:
                        f.write(r.content)
                    return save_path
        except Exception as e:
            logger.warning(f"Thumbnail {size} fail: {e}")
            continue

    return "static/placeholder-thumbnail.jpg"  # 全部失败返回默认图
```

## 3.5 数据流：下载到入库

```mermaid
sequenceDiagram
    autonumber
    participant Sched as 调度器
    participant Worker as run_download_worker
    participant YDL as CancellableYDL
    participant Hook as 进度钩子
    participant DB as SQLite
    participant SSE as SSE 推送
    participant FS as 文件系统
    participant Thumb as thumbnail.py

    Sched->>Worker: 拾取 queued 任务
    Worker->>DB: status=downloading
    Worker->>YDL: extract_info(download=True)
    loop 每个下载片段
        YDL->>Hook: progress_hook(downloading)
        Hook->>DB: UPDATE progress
        Hook->>SSE: 推送进度（前端轮询）
    end
    YDL->>Hook: postprocessor_hook(Merger started)
    Hook->>DB: status=merging
    YDL->>FS: 写最终 MP4
    YDL->>Hook: postprocessor_hook(Merger finished)
    Hook->>DB: 写入 videos 表
    Hook->>Thumb: download_thumbnail(youtube_id)
    Thumb->>FS: 保存 data/thumbnails/{id}.jpg
    Hook->>DB: status=ready
    Hook->>SSE: 推送 ready
```

## 3.6 task_cleaner.py

```python
async def cleanup_old_tasks():
    """每日凌晨 3 点清理：Ready 3 天 / Failed & Cancelled 30 天"""
    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        # Ready 任务保留 3 天
        r1 = (await db.execute(
            delete(DownloadTask).where(
                DownloadTask.status == "ready",
                DownloadTask.finished_at < now - timedelta(days=3)
            )
        )).rowcount
        # Failed / Cancelled 保留 30 天
        r2 = (await db.execute(
            delete(DownloadTask).where(
                DownloadTask.status.in_(["failed", "cancelled"]),
                DownloadTask.finished_at < now - timedelta(days=30)
            )
        )).rowcount
        await db.commit()
        logger.info(f"Task cleanup: removed {r1} ready, {r2} failed/cancelled")
```

---

## Related

- [01-database-schema.md](01-database-schema.md) — 数据模型
- [02-api-design.md](02-api-design.md) — API 签名
- [.learnings/knowledge/yt-dlp-integration.md](../../.learnings/knowledge/yt-dlp-integration.md) — yt-dlp 调研沉淀