# 03. yt-dlp 集成设计

> 核心服务层设计：调度器 + 下载器 + 取消 + 重试。基于需求 02 §2.2 ~ 2.9 + .learnings/yt-dlp-integration.md

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