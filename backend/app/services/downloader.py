"""
yt-dlp 下载器核心实现

- CancellableYDL：子类化 _progress_hook 注入协作式取消
- build_ydl_opts：根据 quality 映射 yt-dlp format 字符串
- run_download_worker：worker 协程，使用 Semaphore + run_in_executor
- 自动重试（3 次退避策略，详见设计文档 §3.3.4 / 需求 02 §2.8）
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta

from app.database import AsyncSessionLocal
from app.models import DownloadTask, Video
from .scheduler import download_semaphore, cancel_events
from .settings import SettingsService

logger = logging.getLogger(__name__)

# 重试退避策略（秒）：第 1 次立即，第 2 次 30s，第 3 次 120s
RETRY_BACKOFFS = {1: 0, 2: 30, 3: 120}

# 默认下载目录（可由 env 覆盖）
DATA_DIR = os.environ.get("TUBEHUB_DATA_DIR", "data/videos")


# ---------------------------------------------------------------------------
# yt-dlp 延迟加载：避免在导入阶段因版本问题崩溃
# ---------------------------------------------------------------------------
def _import_yt_dlp():
    """延迟导入 yt_dlp 模块，便于测试与版本兼容。"""
    import yt_dlp
    return yt_dlp


# ---------------------------------------------------------------------------
# 动态格式解析逻辑（已确认 ✅ 替代静态 QUALITY_MAP 机制）
# ---------------------------------------------------------------------------
def build_ydl_opts(
    task: DownloadTask,
    cookies_path: str | None,
    output_dir: str,
) -> dict:
    """
    v3.0 严格 list-formats 模式：
    - 直接用 task.video_format_id + task.audio_format_id 拼接为 yt-dlp format 表达式
    - 无需考虑 /best 兜底（前端已保证 ID 存在且合法）
    """
    vid = task.video_format_id or "bestvideo"
    aid = task.audio_format_id or "bestaudio"
    fmt = f"{vid}+{aid}"

    return {
        "format": fmt,
        "merge_output_format": "mp4",
        "outtmpl": f"{output_dir}/%(uploader)s/%(title)s [%(id)s].%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "writethumbnail": False,                 # 缩略图由后端单独下载（走代理）

        "cookiefile": cookies_path,
        
        # 绕过 PO-Token 安全限制
        "extractor_args": {
            "youtube": {
                "player_client": ["tv", "android", "web"],
            }
        },

        # 钩子：进度 + 后处理
        "progress_hooks": [lambda d: progress_callback(d, task.id)],
        "postprocessor_hooks": [lambda d: postprocessor_callback(d, task.id)],
    }


# ---------------------------------------------------------------------------
# 取消子化的 YoutubeDL
# ---------------------------------------------------------------------------
def make_cancellable_ydl(cancel_event: asyncio.Event):
    """工厂函数：延迟 import yt_dlp 并返回 CancellableYDL 类。

    便于在不影响测试启动的前提下使用。
    """
    yt_dlp = _import_yt_dlp()

    class CancellableYDL(yt_dlp.YoutubeDL):
        """继承 YoutubeDL，子类化 _progress_hook 注入取消逻辑"""

        def __init__(self, params: dict, **kw):
            super().__init__(params, **kw)
            self._cancel = cancel_event

        def _progress_hook(self, d: dict):
            if self._cancel.is_set():
                raise yt_dlp.utils.DownloadCancelled()
            return super()._progress_hook(d)

    return CancellableYDL


# ---------------------------------------------------------------------------
# 进度 / 后处理回调（在线程池中执行，需通过 call_soon_threadsafe 调度协程）
# ---------------------------------------------------------------------------
def _schedule_coro(coro):
    """把协程安全地扔回主事件循环（hook 在子线程中运行）。"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # 子线程无主循环时退化为直接关闭协程
        coro.close()
        return
    loop.call_soon_threadsafe(asyncio.create_task, coro)


def progress_callback(d: dict, task_id: int) -> None:
    """progress_hooks 回调：更新 DB + 通知 SSE"""
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimated") or 0
        downloaded = d.get("downloaded_bytes", 0)
        percent = (downloaded / total * 100) if total else 0.0
        speed = d.get("_speed_str", "0 B/s")
        eta = d.get("_eta_str", "00:00")

        _schedule_coro(
            update_task_progress(
                task_id, "downloading",
                percent, speed, eta, downloaded, total,
            )
        )
    elif d["status"] == "finished":
        # 单个文件下载完成；合并阶段由 postprocessor_hook 接管
        pass


def postprocessor_callback(d: dict, task_id: int) -> None:
    """postprocessor_hooks 回调：跟踪合并阶段。"""
    pp = d.get("postprocessor")
    if d["status"] == "started":
        _schedule_coro(update_task_status(task_id, "merging"))
    elif d["status"] == "finished" and pp == "Merger":
        filepath = d.get("info_dict", {}).get("filepath")
        _schedule_coro(on_download_finished(task_id, filepath))


# ---------------------------------------------------------------------------
# DB 写入辅助
# ---------------------------------------------------------------------------
async def update_task_progress(
    task_id: int, status: str,
    percent: float, speed: str, eta: str,
    downloaded_bytes: int, total_bytes: int,
) -> None:
    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        if not task:
            return
        task.status = status
        task.progress = percent
        task.speed = speed
        task.eta = eta
        task.downloaded_bytes = downloaded_bytes
        task.total_bytes = total_bytes
        await db.commit()


async def update_task_status(task_id: int, status: str) -> None:
    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        if not task:
            return
        task.status = status
        await db.commit()


async def update_task_title(task_id: int, title: str) -> None:
    """更新下载任务的 title（从 extract_info 提取的真实 YouTube 标题）"""
    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        if not task:
            return
        if task.title != title:
            task.title = title
            await db.commit()


async def mark_task_cancelled(task_id: int) -> None:
    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        if not task:
            return
        task.status = "cancelled"
        task.finished_at = datetime.utcnow()
        await db.commit()
    logger.info(f"Task {task_id} marked cancelled")


async def on_download_finished(task_id: int, filepath: str | None) -> None:
    """合并完成 → 入库 videos 表 + 写 ready。"""
    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        if not task:
            return

        # 1. 写 ready
        task.status = "ready"
        task.finished_at = datetime.utcnow()
        task.save_path = filepath

        # 2. 写 videos（幂等按 youtube_id upsert）
        youtube_id = task.youtube_id
        video = None
        if youtube_id:
            from sqlalchemy import select
            video = (
                await db.execute(select(Video).where(Video.youtube_id == youtube_id))
            ).scalar_one_or_none()

        if not video:
            video = Video(
                youtube_id=youtube_id or f"unknown-{task_id}",
                title=task.title or "Untitled",
                source_url=task.url,
                file_path=filepath or "",
                format_type=task.format_type,
                quality_label=task.quality,
            )
            db.add(video)

        await db.commit()
    logger.info(f"Task {task_id} ready, filepath={filepath}")


async def handle_download_failure(task_id: int, error: str) -> None:
    """失败处理：自动重试 3 次（详见需求 02 §2.8 + 设计文档 §3.3.4）。"""
    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        if not task:
            return

        task.retry_count += 1
        task.error_message = error[:500]
        task.last_attempt_at = datetime.utcnow()

        if task.retry_count <= task.max_retries:
            # 自动重试：先入回 queued 池，按 backoff 延迟再次出队
            task.status = "queued"
            backoff = RETRY_BACKOFFS.get(task.retry_count, 0)
            task.last_attempt_at = datetime.utcnow() + timedelta(seconds=backoff)
            logger.warning(
                f"Task {task_id} auto-retry ({task.retry_count}/{task.max_retries}) "
                f"after {backoff}s"
            )
        else:
            task.status = "failed"
            task.finished_at = datetime.utcnow()
            logger.error(f"Task {task_id} final fail: {error[:200]}")

        await db.commit()


# ---------------------------------------------------------------------------
# Worker 主协程
# ---------------------------------------------------------------------------
async def _get_task(task_id: int) -> DownloadTask | None:
    async with AsyncSessionLocal() as db:
        return await db.get(DownloadTask, task_id)


async def run_download_worker(task_id: int) -> None:
    """下载 worker：受 Semaphore 限制，使用 run_in_executor 同步下载。"""
    cancel_event = asyncio.Event()
    cancel_events[task_id] = cancel_event

    # 延迟：实际尝试下载时才导入 yt_dlp，避免测试环境 import 失败
    try:
        yt_dlp = _import_yt_dlp()
        Cancelled = yt_dlp.utils.DownloadCancelled
    except Exception as e:
        logger.error(f"yt_dlp import failed: {e}")
        await handle_download_failure(task_id, f"yt_dlp unavailable: {e}")
        cancel_events.pop(task_id, None)
        return

    async with download_semaphore:
        try:
            task = await _get_task(task_id)
            if not task:
                logger.warning(f"Task {task_id} not found in DB")
                return

            await update_task_status(task_id, "downloading")

            # 仅拉取 cookies，代理自动由环境变量捕获
            cookies_path = "data/cookies.txt" if os.path.exists("data/cookies.txt") else None

            ydl_opts = build_ydl_opts(task, cookies_path, DATA_DIR)
            logger.info(f"Task {task_id} download config locked - Cookies: {'data/cookies.txt' if cookies_path else 'None'} (env HTTP_PROXY active)")
            CancellableYDL = make_cancellable_ydl(cancel_event)

            loop = asyncio.get_running_loop()

            def _sync_download():
                with CancellableYDL(ydl_opts) as ydl:
                    # 1. 第一步：先 extract_info(download=False) 获取视频全部格式信息 (相当于 --list-formats 探针)
                    logger.info(f"Task {task_id} pre-fetching metadata for dynamic format selection...")
                    info = ydl.extract_info(task.url, download=False)

                    # 2. 第二步：根据真实的 formats 列表，优选出最贴合高度限制的最佳音视频 format id 组合
                    chosen_format = select_dynamic_format(info, task.quality)
                    logger.info(f"Task {task_id} dynamic format matched - Choice: {chosen_format} (Target: {task.quality})")

                    # 动态更新 ydl_opts['format']
                    ydl.params["format"] = chosen_format

                    # 注意：任务入库时已包含真实 title（前置 API 阶段已抓取），
                    # 此处不再自愈 Title

                    # 3. 第三步：真正启动下载
                    logger.info(f"Task {task_id} starting actual stream download with format: {chosen_format}")
                    return ydl.extract_info(task.url, download=True)

            await loop.run_in_executor(None, _sync_download)
            # run_in_executor 成功完成即认为已 finished；
            # postprocessor_hook 通过 on_download_finished 完成入库
        except Cancelled:
            await mark_task_cancelled(task_id)
        except Exception as e:
            logger.exception(f"Worker task {task_id} error: {e}")
            await handle_download_failure(task_id, str(e))
        finally:
            cancel_events.pop(task_id, None)


# ---------------------------------------------------------------------------
# 手动重试 / 任务删除（API 层调用）
# ---------------------------------------------------------------------------
async def reset_task_for_manual_retry(task_id: int) -> bool:
    """
    手动重试入口（被 POST /api/downloads/{id}/retry 调用）：
    - 仅对已结束（failed / cancelled）任务生效
    - 将 retry_count 重置为 0、清理错误信息
    - 状态置回 queued，调度环会自动拾取重新入队
    """
    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        if not task:
            return False
        if task.status not in ("failed", "cancelled"):
            return False

        task.status = "queued"
        task.retry_count = 0
        task.error_message = None
        task.progress = 0.0
        task.downloaded_bytes = 0
        task.speed = None
        task.eta = None
        task.last_attempt_at = datetime.utcnow()
        task.finished_at = None
        await db.commit()
        logger.info(f"Task {task_id} manually retried by user - reset to queued.")
        return True


async def delete_download_task(task_id: int) -> bool:
    """
    物理删除任务记录（被 DELETE /api/downloads/{id} 调用）：
    - 支持删除 finished (ready/failed/cancelled) 状态的任务，清理 DB 占位
    - 进行中 (downloading/merging/queued) 任务拒绝删除，必须先取消
    """
    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        if not task:
            return False
        if task.status in ("downloading", "merging", "queued", "pending"):
            return False
        await db.delete(task)
        await db.commit()
        logger.info(f"Task {task_id} permanently deleted from history.")
        return True


async def cancel_running_task(task_id: int) -> bool:
    """
    取消进行中的任务（被 DELETE /api/downloads/{id} 调用）：
    - 触发 cancel_event 让 worker 协作式中断
    - 立刻将状态置为 cancelled
    """
    # 先通知 cancel_event，让 hook 抛 DownloadCancelled
    evt = cancel_events.get(task_id)
    if evt:
        evt.set()
    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        if not task:
            return False
        task.status = "cancelled"
        task.finished_at = datetime.utcnow()
        await db.commit()
    cancel_events.pop(task_id, None)
    logger.info(f"Task {task_id} cancelled by user.")
    return True
