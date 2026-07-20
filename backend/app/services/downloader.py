"""
yt-dlp 下载器核心实现

- CancellableYDL：子类化 _progress_hook 注入协作式取消
- build_ydl_opts：根据 quality 映射 yt-dlp format 字符串
- run_download_worker：worker 协程，使用 Semaphore + run_in_executor
- 自动重试（3 次退避策略，详见设计文档 §3.3.4 / 需求 02 §2.8）
"""

import asyncio
import glob as _glob
import logging
import os
from datetime import datetime, timedelta, date as _date
from typing import Any

from app.database import AsyncSessionLocal
from app.models import DownloadTask, Video
from .scheduler import download_semaphore, cancel_events

logger = logging.getLogger(__name__)

# 重试退避策略（秒）：第 1 次立即，第 2 次 30s，第 3 次 120s
RETRY_BACKOFFS = {1: 0, 2: 30, 3: 120}

# 默认下载目录（可由 env 覆盖）
DATA_DIR = os.environ.get("TUBEHUB_DATA_DIR", "data/videos")


# ---------------------------------------------------------------------------
# yt-dlp 延迟加载：避免在导入阶段因版本问题崩溃
# ---------------------------------------------------------------------------


def _is_valid_netscape_cookies(file_path: str) -> bool:
    """检查 cookies 文件是否为合法的 Netscape 格式"""
    if not os.path.exists(file_path):
        return False
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # Netscape 格式：至少需要一行 #HttpOnly_ 或 domain tab 行
        for line in lines:
            line = line.strip()
            if not line or line.startswith("# "):
                continue
            # tab 分隔的 7 字段格式：domain  flag  path  secure  expiration  name  value
            if line.startswith("#HttpOnly_") or line.startswith("# Netscape") or "\t" in line:
                return True
        return False
    except Exception as e:
        logger.warning(f"Cookie 文件读取失败 ({file_path}): {e}")
        return False
def _import_yt_dlp():
    """延迟导入 yt_dlp 模块，便于测试与版本兼容。"""
    import yt_dlp
    return yt_dlp


def _parse_upload_date(raw: object) -> "_date | None":
    """将 yt-dlp 的 upload_date 字符串（如 '20231015'）转为 Python date 对象。

    SQLAlchemy Date 列只接受 datetime.date，不接受字符串。
    """
    if raw is None:
        return None
    if isinstance(raw, _date):
        return raw
    try:
        s = str(raw).strip()
        if len(s) == 8:
            return _date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except (ValueError, TypeError):
        pass
    return None


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
        "outtmpl": f"{output_dir}/%(uploader).30B/%(title).80B [%(id)s].%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "writethumbnail": False,

        "cookiefile": cookies_path,
        # 禁止 yt-dlp 更新/覆写 cookies 文件（否则会把有效 cookies 替换为空文件）
        "no_cookies_update": True,

        # 允许 deno 从 GitHub 下载 EJS challenge solver
        "remote_components": ["ejs:github"],

        # 增强容错：分片 403 时重试，不因单片失败中断整个下载
        "skip_unavailable_fragments": True,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 5,

        # 不限制 player_client，让 yt-dlp 自动选最优客户端
        # （android_vr 不需要 n-challenge/EJS，通常最稳定）

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
# Module-level main loop reference (由 worker 在主线程设置)
# ---------------------------------------------------------------------------
MAIN_LOOP = None


def _schedule_coro(coro):
    """把协程安全地扔回主事件循环（hook 在子线程中运行）。

    使用模块级 MAIN_LOOP 引用，而不是 asyncio.get_event_loop()，
    因为后者在子线程中会创建新循环，导致调度永远不生效。
    """
    loop = MAIN_LOOP
    if loop is None or loop.is_closed():
        # 兜底：尝试获取当前线程的主循环（兼容老路径）
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            coro.close()
            return
    try:
        future = asyncio.run_coroutine_threadsafe(coro, loop)

        def _on_done(f):
            if f.cancelled():
                logger.debug("_schedule_coro: scheduled coroutine was cancelled")
                return
            exc = f.exception()
            if exc:
                logger.error("_schedule_coro: scheduled coroutine raised: %s", exc, exc_info=exc)

        future.add_done_callback(_on_done)
    except RuntimeError:
        coro.close()
# ---------------------------------------------------------------------------

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
        # 单个文件（视频轨或音频轨）下载完成；合并阶段由 postprocessor_hook 接管
        filename = d.get("filename") or d.get("tmpfilename") or ""
        logger.info("Task %s: file download finished (%s)", task_id, os.path.basename(str(filename))[:60])


def postprocessor_callback(d: dict, task_id: int) -> None:
    """postprocessor_hooks 回调：跟踪合并阶段。"""
    pp = d.get("postprocessor")
    status = d.get("status")
    logger.debug("postprocessor_callback task=%s pp=%s status=%s", task_id, pp, status)
    # 仅在真正进入合并后处理器时切换为 merging，避免被其他 postprocessor 误伤
    if status == "started" and pp == "Merger":
        logger.info("Task %s Merger started → merging", task_id)
        _schedule_coro(update_task_status(task_id, "merging"))
    elif status == "finished" and pp == "Merger":
        filepath = d.get("info_dict", {}).get("filepath")
        info_dict = d.get("info_dict")
        logger.info("Task %s Merger finished → filepath=%s", task_id, filepath)
        _schedule_coro(on_download_finished(task_id, filepath, info_dict))


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


async def on_download_finished(task_id: int, filepath: str | None, info_dict: dict | None = None) -> None:
    """合并完成 → 入库 videos 表 + 写 ready。

    info_dict: yt-dlp extract_info 返回值，用于提取 duration/uploader/width/height。
    """
    from app.services.thumbnail import THUMBNAIL_DIR, download_thumbnail
    import os

    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        if not task:
            return
        # 幂等保护：避免 hook 与 worker fallback 重复收尾
        if task.status == "ready":
            if filepath and task.save_path != filepath:
                task.save_path = filepath
                await db.commit()
            return

        # 1. 写 ready
        task.status = "ready"
        task.finished_at = datetime.utcnow()
        task.save_path = filepath

        # 2. 确定缩略图本地路径（任务创建时已预下载，直接复用）
        youtube_id = task.youtube_id
        thumbnail_path: str | None = None
        if youtube_id:
            candidate = os.path.join(THUMBNAIL_DIR, f"{youtube_id}.jpg")
            if os.path.exists(candidate):
                thumbnail_path = candidate

        # 3. 从 yt-dlp info_dict 提取视频元数据
        meta: dict = {}
        if isinstance(info_dict, dict):
            meta = {
                "duration": info_dict.get("duration"),
                "uploader": info_dict.get("uploader") or info_dict.get("channel"),
                "uploader_id": info_dict.get("uploader_id") or info_dict.get("channel_id"),
                "upload_date": _parse_upload_date(info_dict.get("upload_date")),
                "width": info_dict.get("width"),
                "height": info_dict.get("height"),
                "fps": info_dict.get("fps"),
                "description": (info_dict.get("description") or "")[:4096] or None,
            }
            # file_size：优先从 info_dict 取，否则读磁盘
            requested = info_dict.get("requested_downloads") or []
            if requested and isinstance(requested[0], dict):
                meta["file_size"] = requested[0].get("filesize")
            if not meta.get("file_size") and filepath and os.path.exists(filepath):
                meta["file_size"] = os.path.getsize(filepath)
        elif filepath and os.path.exists(filepath):
            meta["file_size"] = os.path.getsize(filepath)

        # 4. 写 videos（幂等按 youtube_id upsert）
        video = None
        if youtube_id:
            from sqlalchemy import select
            video = (
                await db.execute(select(Video).where(Video.youtube_id == youtube_id))
            ).scalar_one_or_none()

        if not video:
            # filepath 为 None 时也创建记录，但 file_path 保持为空；
            # 后续 ffprobe backfill 会在下次启动时补全元数据，
            # 播放时若 file_path 为空会返回 404（明确失败比静默丢失好）
            video = Video(
                youtube_id=youtube_id or f"unknown-{task_id}",
                title=task.title or "Untitled",
                source_url=task.url,
                file_path=filepath or "",
                thumbnail_path=thumbnail_path,
                video_format_id=task.video_format_id,
                audio_format_id=task.audio_format_id,
                **{k: v for k, v in meta.items() if v is not None},
            )
            db.add(video)
            if not filepath:
                logger.warning(
                    "Task %s: Video created without file_path (filepath=None); "
                    "stream endpoint will 404 until file_path is updated",
                    task_id,
                )
        else:
            # 已存在则补全/更新字段（只在有新值时更新 file_path）
            if filepath:
                video.file_path = filepath
            if thumbnail_path:
                video.thumbnail_path = thumbnail_path
            for k, v in meta.items():
                if v is not None:
                    setattr(video, k, v)

        await db.commit()

    duration_str = f"{meta.get('duration')}s" if meta.get('duration') else "unknown"
    logger.info(
        "Task %s ready: filepath=%s duration=%s uploader=%s",
        task_id, filepath, duration_str, meta.get("uploader") or "unknown",
    )


def _extract_output_filepath(info: Any) -> str | None:
    """从 yt-dlp extract_info 返回值中尽力提取最终输出文件路径。"""
    if not isinstance(info, dict):
        return None

    candidates: list[str] = []

    for key in ("filepath", "_filename"):
        value = info.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)

    requested = info.get("requested_downloads")
    if isinstance(requested, list):
        for item in requested:
            if not isinstance(item, dict):
                continue
            for key in ("filepath", "_filename"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    candidates.append(value)

    # 优先返回真实存在的路径
    for path in candidates:
        if os.path.exists(path):
            return path

    return candidates[0] if candidates else None


async def _scan_video_file(youtube_id: str | None) -> str | None:
    """当 info_dict 无法提供文件路径时，在磁盘上扫描已下载的视频文件。"""
    if not youtube_id:
        return None
    patterns = [
        f"{DATA_DIR}/**/*{youtube_id}*.mp4",
        f"{DATA_DIR}/**/*{youtube_id}*.mkv",
        f"{DATA_DIR}/**/*{youtube_id}*.webm",
    ]
    for pattern in patterns:
        matches = _glob.glob(pattern, recursive=True)
        for path in matches:
            # 排除临时文件
            if not (path.endswith(".part") or ".f1" in os.path.basename(path)):
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    return path
    return None


async def _finalize_after_worker_success(task_id: int, info: Any) -> None:
    """worker 成功返回后的兜底收尾，防止 postprocessor hook 丢事件导致卡住。"""
    filepath = _extract_output_filepath(info)
    # info 本身就是 yt-dlp 的 info_dict，透传给 on_download_finished 以提取元数据
    info_dict = info if isinstance(info, dict) else None

    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        if not task:
            logger.warning("_finalize_after_worker_success: task %s not found", task_id)
            return
        current_status = task.status  # session 内读取，避免 detached 对象
        youtube_id = task.youtube_id

    # filepath 为 None 时（info_dict 为空/续传场景），扫描磁盘查找文件
    if not filepath:
        filepath = await _scan_video_file(youtube_id)
        if filepath:
            logger.info(
                "_finalize_after_worker_success: filepath recovered by disk scan for task %s: %s",
                task_id, filepath,
            )
        else:
            logger.warning(
                "_finalize_after_worker_success: cannot find file for task %s (youtube_id=%s)",
                task_id, youtube_id,
            )

    logger.info(
        "_finalize_after_worker_success task=%s status=%s filepath=%s",
        task_id, current_status, filepath,
    )

    if current_status == "ready":
        logger.debug("Task %s already ready, skip fallback finalize", task_id)
        return
    if current_status == "cancelled":
        logger.debug("Task %s cancelled, skip fallback finalize", task_id)
        return

    logger.warning(
        "Task %s: worker finished but status=%s (hook may have been lost), "
        "applying fallback finalize (filepath=%s)",
        task_id, current_status, filepath,
    )
    await on_download_finished(task_id, filepath, info_dict)


async def handle_download_failure(task_id: int, error: str) -> None:
    """失败处理：自动重试 3 次（详见需求 02 §2.8 + 设计文档 §3.3.4）。"""
    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        if not task:
            return

        # 防止竞争：若 postprocessor_hook 已经把任务推到 ready，
        # 则不应再标记失败
        if task.status in ("ready", "cancelled"):
            logger.info(
                "handle_download_failure: task %s already in status=%s, skipping failure",
                task_id, task.status,
            )
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

            # cookies：从 DB 读取到临时文件备用（防止被 yt-dlp 覆写磁盘文件）
            from app.services.scraper import _get_cookies_path
            cookies_path = _get_cookies_path()

            loop = asyncio.get_running_loop()
            # 关键:把主循环引用保存到模块级变量,供子线程中的 progress_hooks 使用
            import app.services.downloader as _dl_mod
            _dl_mod.MAIN_LOOP = loop

            def _make_sync_download(cp: str | None):
                """构造下载函数（cp=cookies_path 或 None）。"""
                ydl_opts = build_ydl_opts(task, cp, DATA_DIR)
                CancellableYDL = make_cancellable_ydl(cancel_event)
                chosen_format = f"{task.video_format_id}+{task.audio_format_id}"

                def _run():
                    with CancellableYDL(ydl_opts) as ydl:
                        ydl.params["format"] = chosen_format
                        logger.info(
                            f"Task {task_id} download start: format={chosen_format} "
                            f"cookies={'yes' if cp else 'no'}"
                        )
                        try:
                            return ydl.extract_info(task.url, download=True)
                        except Exception as exc:
                            err = str(exc)
                            # 格式不可用时 fallback：尝试 video_format_id + bestaudio
                            if "Requested format is not available" in err:
                                fallback = f"{task.video_format_id}+bestaudio"
                                logger.warning(
                                    "Task %s: format %s unavailable, fallback to %s",
                                    task_id, chosen_format, fallback,
                                )
                                ydl.params["format"] = fallback
                                return ydl.extract_info(task.url, download=True)
                            raise
                return _run

            # 第一次：不带 cookies（android_vr 对公开视频无需认证）
            info_dict = None
            try:
                info_dict = await loop.run_in_executor(None, _make_sync_download(None))
            except Cancelled:
                await mark_task_cancelled(task_id)
                return
            except Exception as e:
                err_str = str(e)
                # Bot 检测或需要登录 → 带 cookies 重试
                if ("Sign in" in err_str or "bot" in err_str.lower() or
                        "confirm" in err_str.lower() or "403" in err_str) and cookies_path:
                    logger.warning(
                        f"Task {task_id}: download failed without cookies ({err_str[:80]}), "
                        f"retrying with cookies"
                    )
                    # 重置进度再重试
                    await update_task_status(task_id, "downloading")
                    try:
                        info_dict = await loop.run_in_executor(
                            None, _make_sync_download(cookies_path)
                        )
                    except Cancelled:
                        await mark_task_cancelled(task_id)
                        return
                    except Exception as e2:
                        raise e2  # cookies 也失败，走正常失败处理
                else:
                    raise  # 其他错误直接走失败处理
            # 正常情况下 postprocessor_hook 会把任务推到 ready。
            # 兜底：若 hook 丢失/未触发（尤其是带 cookies 重试续传场景），
            # worker 成功返回后强制收尾，避免卡在 downloading/merging。
            # info_dict 为 None 时（yt-dlp 续传模式）也强制收尾，让 ffprobe 补充元数据。
            await _finalize_after_worker_success(task_id, info_dict or {})
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


async def delete_download_task(task_id: int, allow_in_progress: bool = False) -> bool:
    """
    物理删除任务记录（被 DELETE /api/downloads/{id} 调用）：
    - 默认仅删除 finished (ready/failed/cancelled) 状态
    - 若 allow_in_progress=True，可删除失联的进行中任务（无活跃 worker 的僵尸任务）
    """
    async with AsyncSessionLocal() as db:
        task = await db.get(DownloadTask, task_id)
        if not task:
            return False
        if (not allow_in_progress) and task.status in ("downloading", "merging", "queued", "pending"):
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
