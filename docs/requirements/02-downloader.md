# 02. 下载器需求

> 来源：用户需求 §2, §6, §7, §8

## 2.1 核心要求

| 项 | 说明 |
|----|------|
| 下载库 | **yt-dlp Python 模块**（在 venv 中通过 `pip install yt-dlp`） |
| 支持的 URL | YouTube 单视频、YouTube 歌单（多视频批量下载） |
| 格式与清晰度 | 用户在添加时显式选择（见 §2.2） |
| 并发策略 | **最多 2 个任务并行**，超出排队等待，详见 [§2.2.3](#223-并发调度已确认) |
| 进度汇报 | 通过 yt-dlp 的 `progress_hooks` 回调实时更新 |

## 2.2 格式与清晰度选项（用户需求 §8）

> 用户在添加下载时需选择，**前端必须提供该对话框**

### 2.2.1 格式（format_type）

> 决策（2026-07-07）：**专攻视频下载**，不考虑支持下载"仅音频"格式。

| 取值 | 说明 |
|------|------|
| `video` | 视频 + 音频（自动合并，默认） |

### 2.2.2 清晰度（quality）

> 与 yt-dlp 的 format selection 对应

| UI 选项 | yt-dlp `format` 字符串 | 实际画质 |
|---------|------------------------|----------|
| `best` | `bestvideo+bestaudio/best` | 最高画质（4K/8K） |
| `1080p` | `bestvideo[height<=1080]+bestaudio/best[height<=1080]` | 1080p 及以下最高 |
| `720p` | `bestvideo[height<=720]+bestaudio/best[height<=720]` | 720p 及以下最高 |
| `480p` | `bestvideo[height<=480]+bestaudio/best[height<=480]` | 480p 及以下最高 |
| `worst` | `worstvideo+worstaudio/worst` | 最低画质（节省空间） |

### 2.2.3 并发调度（已确认 ✅）

#### 任务并行上限

- **同时最多 2 个任务** 处于 `downloading` 或 `merging` 状态
- 超出部分进入 **`queued`** 状态（新增），按 FIFO 顺序等待
- 当有任务结束时（`Ready` / `Failed` / `Cancelled`），调度器从队列拾取最早的任务进入 `Pending` → `Downloading`

#### 歌单（Playlist）行为

- **串行下载**：歌单解析出的所有视频依次入队，前一首完成后再下载下一首
- 任务列表中**扁平展示**：所有子任务（无论是单视频还是歌单拆解出的子任务）均以独立行展示，无分组、无层级
- 任一首失败不影响其他子任务，失败子任务独立显示、可独立重试
- 整个歌单取消 = 取消所有未开始的子任务 + 停止当前进行中的子任务

#### 视频原始链接保留

为避免后期分享、重新下载或比对，所有下载任务都必须将用户提交的**原始 URL** 持久化。

- `download_tasks.url` 保留用户提交的原始 URL（单视频 URL 或歌单 URL）
- `videos.source_url` 保存入库时该视频对应的原始 YouTube URL（单视频的 watch?v=xxx 或 shorts/xxx）
- 下载完成后，前端可通过点击"复制 YouTube 链接"按钮复制该 URL

#### 实现：asyncio + Semaphore（已确认 ✅）

> 决策（2026-07-07）：**`asyncio.create_task` 启动无限循环调度协程 + 全局 `Semaphore(2)` 控制并发**。
> 这是最贴合 FastAPI 异步生态的方案，无需引入 Celery + Redis。

```python
# services/scheduler.py
import asyncio
from contextlib import asynccontextmanager

# 全局信号量，限制同时下载的任务数
download_semaphore = asyncio.Semaphore(2)

# 取消事件池：task_id -> asyncio.Event
cancel_events: dict[int, asyncio.Event] = {}


@asynccontextmanager
async def acquire_download_slot(task_id: int):
    """worker 协程入口：获取信号量 + 注册取消事件"""
    cancel_event = asyncio.Event()
    cancel_events[task_id] = cancel_event
    try:
        async with download_semaphore:
            yield cancel_event  # 传出去让 hook 检查
    finally:
        cancel_events.pop(task_id, None)


async def scheduler_loop():
    """调度主循环：每 1 秒检查 queued 任务并启动 worker"""
    while True:
        try:
            slots_available = download_semaphore._value  # 剩余槽位
            if slots_available <= 0:
                await asyncio.sleep(1)
                continue

            # 取出最早 queued 任务
            async with AsyncSessionLocal() as db:
                stmt = (select(DownloadTask)
                        .where(DownloadTask.status == "queued")
                        .order_by(DownloadTask.created_at.asc())
                        .limit(slots_available))
                tasks = (await db.execute(stmt)).scalars().all()

                for task in tasks:
                    task.status = "pending"
                    await db.commit()
                    # 启动 worker 协程（不阻塞调度循环）
                    asyncio.create_task(run_download_worker(task.id))

        except Exception as e:
            logger.exception(f"scheduler_loop error: {e}")
        await asyncio.sleep(1)


async def run_download_worker(task_id: int):
    """单个下载 worker，受 Semaphore 控制"""
    async with acquire_download_slot(task_id) as cancel_event:
        await download_single_task(task_id, cancel_event)
```

#### FastAPI 启动钩子

```python
# app/main.py
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时拉起调度循环
    task = asyncio.create_task(scheduler_loop())
    yield
    # 关闭时取消
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)
```

#### 取消任务

```python
# api/downloads.py
@router.post("/{task_id}/cancel")
async def cancel_task(task_id: int):
    evt = cancel_events.get(task_id)
    if evt:
        evt.set()                    # 通知 hook 抛 DownloadCancelled
    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        task.status = "cancelled"
        await db.commit()
    return {"cancelled": True}
```

#### 失败任务处理（已确认 ✅）

- **自动重试 3 次**（已确认 ✅）：单次任务失败后自动重新入队，最多 3 次；超过后状态置为 `Failed`
- **失败保留**：Failed 任务保留在列表中 30 天后清理（详见 §2.9）
- **手动重试**：用户点击"重试"按钮 → `retry_count` 重置为 0，状态置回 `queued`，重新进入调度
- 失败原因写入 `error_message`，前端可展示
- 连续失败次数在 UI 上以红色徽标提示（详见 [01-frontend.md §1.2.2](01-frontend.md)）

---

## 2.3 下载任务状态机（已确认 ✅ 含自动重试）

```
                        ┌─► Queued (等待调度) ─┐
                        │                       ▼
新建 ──► Pending ──────┴─────────────► Downloading ──► Merging ──► Ready
                │                              │              │
                ▼                              ▼              ▼
            Cancelled                       Cancelled       Failed ─┐
                                                                          │
                                              ┌───────────────┘
                                              ▼ retry_count < 3 且未手动
                                          Queued (自动重试)
                                              │
                                              ▼ retry_count == 3
                                          Failed (终态，可手动重启)

| 状态 | 说明 | DB 字段 `status` |
|------|------|------------------|
| Pending | 任务已创建，等待调度器拾取（瞬态，几乎不可见） | `pending` |
| **Queued** | **等待调度（并发槽位满时进入）** | `queued` |
| Downloading | yt-dlp 正在下载 | `downloading` |
| Merging | FFmpeg 正在合并音视频 / 转码 | `merging` |
| Ready | 视频已落盘，可供播放 | `ready` |
| Failed | 下载或合并失败（保留在任务列表，等待手动重试） | `failed` |
| Cancelled | 用户取消 | `cancelled` |

## 2.4 进度数据（DB 字段）

```python
class DownloadTask:
    id: int                     # 主键
    url: str                    # 原始 YouTube URL
    video_id: str               # YouTube video_id（用于关联 Video）
    title: str                  # 任务创建时的标题（可能被更新）
    format_type: str            # video | audio
    quality: str                # best | 1080p | 720p | ...
    status: str                 # 见上表
    progress: float             # 0.0 - 100.0
    speed: str                  # "1.2 MiB/s"（人类可读）
    eta: str                    # "00:01:23"（人类可读）
    downloaded_bytes: int
    total_bytes: int            # -1 表示未知
    error_message: str          # 失败原因
    save_path: str              # 视频文件最终路径
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
```

## 2.5 API 接口

| Method | Path | 用途 |
|--------|------|------|
| POST | `/api/downloads` | 创建下载任务 |
| GET | `/api/downloads` | 列出所有任务（支持 status 过滤） |
| GET | `/api/downloads/{id}` | 任务详情 |
| DELETE | `/api/downloads/{id}` | 取消任务（若进行中）/ 删除记录（若已完成） |
| POST | `/api/downloads/{id}/retry` | 重新提交失败任务 |
| GET | `/api/downloads/{id}/stream` | SSE 实时进度流 |

## 2.6 错误处理

| 场景 | 行为 |
|------|------|
| URL 非法 | API 返回 400，error_message 写入 DB |
| 视频不存在 / 私密 | 任务标记 Failed，error_message 记录原因 |
| 网络中断 | yt-dlp 自动重试 3 次，仍失败则标记 Failed |
| 磁盘空间不足 | 预检查时检测，任务直接进入 Failed |
| yt-dlp 版本过期 | 后端启动时检测版本，提示用户更新 |

---

## 2.7 yt-dlp Python 集成细则（已确认 ✅）

### 2.7.1 核心调用逻辑

```python
import yt_dlp
import asyncio

async def download_video_async(url: str, save_dir: str, task_id: int, cancel_event: asyncio.Event, cookies_path: str = None, proxy_url: str = None):
    """
    异步非阻塞方式调用 yt-dlp。
    使用 loop.run_in_executor 将同步阻塞的 ytdlp 下载转移到线程池中运行。
    """
    loop = asyncio.get_running_loop()
    
    # 1. 配置项
    ydl_opts = {
        'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]', # 限制 1080p
        'merge_output_format': 'mp4',  # 合并为 mp4
        'outtmpl': f'{save_dir}/%(uploader)s/%(title)s [%(id)s].%(ext)s', # 文件命名
        'quiet': True,
        'no_warnings': True,
        'cookiefile': cookies_path,
        'proxy': proxy_url,
        
        # 注册进度钩子（进度汇报）
        'progress_hooks': [lambda d: progress_callback(d, task_id, cancel_event)],
        # 注册后处理钩子（音视频合并/转码）
        'postprocessor_hooks': [lambda d: postprocessor_callback(d, task_id)],
    }
    
    # 2. 线程池下载
    def _sync_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=True)
            
    try:
        info_dict = await loop.run_in_executor(None, _sync_download)
        return info_dict
    except yt_dlp.utils.DownloadCancelled:
        # 捕获用户主动取消异常
        logger.info(f"Task {task_id} 已成功取消")
        raise
    except Exception as e:
        logger.error(f"Task {task_id} 失败: {e}")
        raise
```

### 2.7.2 进度获取：`progress_hooks`

yt-dlp 进度钩子会在**每下载一小段分片（Fragment）**时触发，回调参数为字典 `d`。

```python
# 数据回传与更新逻辑
def progress_callback(d: dict, task_id: int, cancel_event: asyncio.Event):
    # 1. 检测用户取消指令（协程协作式取消）
    if cancel_event.is_set():
        raise yt_dlp.utils.DownloadCancelled() # 抛出此异常，yt-dlp 会中止并自动清理临时文件
        
    if d['status'] == 'downloading':
        # 提取关键字段
        total = d.get('total_bytes') or d.get('total_bytes_estimated') or 0
        downloaded = d.get('downloaded_bytes', 0)
        percent = (downloaded / total * 100) if total else 0.0
        
        # 下划线开头的字段是 yt-dlp 内部格式化好的字符串，可直接用于展示
        speed = d.get('_speed_str', '0 B/s')  # 例如 "1.2 MiB/s"
        eta = d.get('_eta_str', '00:00')      # 例如 "01:23"
        
        # 2. 异步上报：将进度数据批量写入数据库、并通过 SSE 推送给前端
        # （注：由于 hook 运行在子线程，需通过线程安全方式调用后端更新，或存入内存 queue 中）
        update_db_task_progress(
            task_id=task_id,
            status="downloading",
            progress=percent,
            speed=speed,
            eta=eta,
            downloaded_bytes=downloaded,
            total_bytes=total
        )
```

### 2.7.3 后处理获取（合并音频视频）：`postprocessor_hooks`

`finished` 进度钩子仅代表单个视频或音频流下载完毕。对于 1080p，音视频流是**分开下载后通过 FFmpeg 合并**的。

```python
def postprocessor_callback(d: dict, task_id: int):
    # postprocessor 类型（如 ffmpeg Merger, EmbedSubtitle 等）
    pp_name = d.get('postprocessor')
    
    if d['status'] == 'started':
        # 状态流转为合并中
        update_db_task_status(task_id, status="merging")
    elif d['status'] == 'finished' and pp_name == 'Merger':
        # 合并彻底完成，准备入库
        pass
```

### 2.7.4 歌单（Playlist）解析

在点击"开始下载"前，需要调用 `extract_info` 先获取元数据并判断是否为歌单：

```python
def parse_youtube_url(url: str, cookies_path: str = None, proxy_url: str = None) -> dict:
    """仅解析元数据（不下载）"""
    ydl_opts = {
        'extract_flat': 'in_playlist', # 极速解析：仅获取歌单内每个视频的 ID/标题/时长，不下载
        'quiet': True,
        'cookiefile': cookies_path,
        'proxy': proxy_url,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)
```

- 若返回结构中 `_type == 'playlist'`：
  - 遍历 `entries`，取出每个子项的 `id` 与 `title`
  - 向数据库循环写入 `download_tasks` 记录（扁平展示，状态全为 `queued`）
  - 返回子任务数量和标题列表
- 若返回结构中无 `_type`（单视频）：
  - 正常提交单个 `queued` 任务

---

## 2.8 自动重试策略（已确认 ✅）

> 决策（2026-07-07）：**单次任务下载失败后自动重试 3 次**（累计 4 次尝试），超过后任务置为 `Failed`，用户可手动重启。

### 2.8.1 重试字段

在 `download_tasks` 表中新增字段：

```python
class DownloadTask:
    ...
    retry_count: int = 0          # 已重试次数
    max_retries: int = 3          # 最大自动重试次数
    last_attempt_at: datetime     # 最近一次尝试时间（用于计算下次重试退避）
```

### 2.8.2 重试触发逻辑

```python
async def run_download_worker(task_id: int):
    async with acquire_download_slot(task_id) as cancel_event:
        try:
            await download_single_task(task_id, cancel_event)
            # download_single_task 成功后由其内部将 status 置为 Ready
        except DownloadCancelled:
            await mark_task_cancelled(task_id)
            return
        except Exception as e:
            # 失败处理
            async with AsyncSessionLocal() as db:
                task = await db.get(DownloadTask, task_id)
                task.retry_count += 1
                task.error_message = str(e)[:500]
                if task.retry_count <= task.max_retries:
                    # 自动重试：状态置回 queued，重新进入调度
                    task.status = "queued"
                    logger.warning(
                        f"Task {task_id} failed, auto retry "
                        f"({task.retry_count}/{task.max_retries}): {e}"
                    )
                else:
                    # 超过最大重试，置为终态 Failed
                    task.status = "failed"
                    logger.error(f"Task {task_id} final fail after {task.retry_count} retries")
                await db.commit()
```

### 2.8.3 重试退避策略（建议）

为避免对 YouTube 服务器造成压力，连续失败之间应有退避延迟：

| 重试次数 | 退避延迟 |
|----------|----------|
| 第 1 次失败 → 第 2 次尝试 | 立即重试 |
| 第 2 次失败 → 第 3 次尝试 | 等待 30 秒 |
| 第 3 次失败 → 第 4 次尝试 | 等待 2 分钟 |

> 实现方式：在 `queued` 任务上记录 `next_attempt_at`，调度器只拾取 `next_attempt_at <= now()` 的任务。

### 2.8.4 手动重启（终极方案）

- 用户在 UI 上点击"重试"按钮（Failed 任务可显示该按钮）
- API `POST /api/downloads/{id}/retry`：
  - `retry_count` 重置为 0（不算入自动重试历史）
  - `status` 置回 `queued`
  - `error_message` 清空
  - 重新进入调度

---

## 2.9 任务记录保留与清理（已确认 ✅）

> 决策（2026-07-07）：**Ready 任务永久保留 3 天后清理；Failed/Cancelled 任务保留 30 天后清理**。

### 2.9.1 保留策略表

| 终态 | 保留时长 | 清理后行为 |
|------|----------|------------|
| `Ready` | **3 天** | 清理后视频仍在 `videos` 表中（独立入库），仅清理 `download_tasks` 记录 |
| `Failed` | **30 天** | 直接清理记录 |
| `Cancelled` | **30 天** | 直接清理记录 |

> 说明：Ready 任务的视频文件已在下载完成瞬间入库到 `videos` 表，所以 `download_tasks` 中 Ready 记录的清理不影响视频可访问。

### 2.9.2 自动清理实现

```python
# services/task_cleaner.py
from datetime import datetime, timedelta
from sqlalchemy import delete

async def cleanup_old_tasks():
    """每日凌晨 3:00 清理过期任务记录"""
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        # Ready 任务保留 3 天
        ready_cutoff = now - timedelta(days=3)
        # Failed/Cancelled 保留 30 天
        other_cutoff = now - timedelta(days=30)

        # 删除旧 Ready 任务
        stmt1 = delete(DownloadTask).where(
            DownloadTask.status == "ready",
            DownloadTask.finished_at < ready_cutoff,
        )
        r1 = (await db.execute(stmt1)).rowcount

        # 删除旧 Failed/Cancelled 任务
        stmt2 = delete(DownloadTask).where(
            DownloadTask.status.in_(["failed", "cancelled"]),
            DownloadTask.finished_at < other_cutoff,
        )
        r2 = (await db.execute(stmt2)).rowcount

        await db.commit()
        logger.info(f"Task cleanup: removed {r1} ready, {r2} failed/cancelled")
```

### 2.9.3 调度

与 `history_cleaner` 共用 APScheduler，注册 cron `0 3 * * *` 每日凌晨 3 点执行。

---

## Related

- [00-overview.md](00-overview.md) — 项目总览
- [03-library.md](03-library.md) — 下载完成后如何入库
- [07-backend.md](07-backend.md) — 异步任务调度实现