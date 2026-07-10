"""后台定时清理任务

- task_cleaner_loop：每小时扫描，清理 Ready(3天) / Failed|Cancelled(30天) 的下载任务记录
- history_cleaner_loop：每小时扫描，清理 30 天前的播放历史
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models import DownloadTask, PlayHistory

logger = logging.getLogger(__name__)

# 各状态保留时长（天）
_READY_KEEP_DAYS = 3
_FAILED_KEEP_DAYS = 30
_HISTORY_KEEP_DAYS = 30


async def _cleanup_tasks() -> None:
    """清理过期的 download_tasks 记录（不删视频文件，仅删任务流水）。"""
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        # Ready 任务：保留 3 天
        r1 = (await db.execute(
            delete(DownloadTask).where(
                DownloadTask.status == "ready",
                DownloadTask.finished_at < now - timedelta(days=_READY_KEEP_DAYS),
            )
        )).rowcount

        # Failed / Cancelled 任务：保留 30 天
        r2 = (await db.execute(
            delete(DownloadTask).where(
                DownloadTask.status.in_(["failed", "cancelled"]),
                DownloadTask.finished_at < now - timedelta(days=_FAILED_KEEP_DAYS),
            )
        )).rowcount

        await db.commit()

    if r1 or r2:
        logger.info("task_cleaner: removed %d ready, %d failed/cancelled", r1, r2)


async def _cleanup_history() -> None:
    """清理 30 天前的播放历史记录。"""
    cutoff = datetime.utcnow() - timedelta(days=_HISTORY_KEEP_DAYS)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(PlayHistory).where(PlayHistory.last_watched_at < cutoff)
        )
        await db.commit()

    if result.rowcount:
        logger.info("history_cleaner: removed %d expired records", result.rowcount)


async def task_cleaner_loop() -> None:
    """每小时清理一次过期任务记录。"""
    while True:
        try:
            await _cleanup_tasks()
        except Exception as e:  # noqa: BLE001
            logger.warning("task_cleaner_loop error: %s", e)
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("task_cleaner_loop cancelled")
            raise


async def history_cleaner_loop() -> None:
    """每小时清理一次过期播放历史。"""
    while True:
        try:
            await _cleanup_history()
        except Exception as e:  # noqa: BLE001
            logger.warning("history_cleaner_loop error: %s", e)
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("history_cleaner_loop cancelled")
            raise
