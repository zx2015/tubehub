"""
yt-dlp 下载调度器

- 维护全局 Semaphore 限制并发下载数（默认 2）
- 维护 cancel_events 池，提供协作式取消能力
- scheduler_loop 每 1 秒扫描一次 queued 任务，按 FIFO 推进
- 强引用集合 _worker_tasks 防止 create_task 被 GC
- stuck_pending_recovery 每 30s 将卡住的 pending 任务回滚到 queued
"""

import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models import DownloadTask

logger = logging.getLogger(__name__)

# 全局信号量：限制同时 downloading 的任务数（详见需求 02 §2.6）
CONCURRENCY = 2
download_semaphore = asyncio.Semaphore(CONCURRENCY)

# 取消事件池：worker 协程可通过它优雅终止
cancel_events: dict[int, asyncio.Event] = {}

# 强引用集合：防止 create_task 返回的 Task 对象被 GC 回收
_worker_tasks: set[asyncio.Task] = set()

# pending 超时阈值（秒）：超过此时间仍是 pending 的任务视为卡死
_PENDING_TIMEOUT_SECS = 30


def _get_worker():
    """延迟导入：避免 scheduler <-> downloader 循环依赖。"""
    from .downloader import run_download_worker
    return run_download_worker


def _free_slots() -> int:
    """返回当前可用并发槽位数。

    不使用 `semaphore._value`（私有属性，Python 3.13+ 不稳定），
    改用 CONCURRENCY 减去当前活跃 worker 数量。
    """
    active = sum(1 for t in _worker_tasks if not t.done())
    return max(0, CONCURRENCY - active)


async def _recover_stuck_pending() -> None:
    """将卡住的 pending 任务（超过 _PENDING_TIMEOUT_SECS）回滚到 queued。

    场景：worker 在 create_task 前后崩溃，任务状态留在 pending 无人处理。
    """
    cutoff = datetime.utcnow() - timedelta(seconds=_PENDING_TIMEOUT_SECS)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(DownloadTask)
                .where(
                    DownloadTask.status == "pending",
                    DownloadTask.updated_at < cutoff,
                )
                .values(status="queued")
            )
            if result.rowcount:
                await db.commit()
                logger.warning(
                    "stuck-recovery: rolled back %d pending task(s) to queued",
                    result.rowcount,
                )
    except Exception as e:  # noqa: BLE001
        logger.warning("stuck-recovery error: %s", e)


async def scheduler_loop() -> None:
    """每 1 秒检查一次 queued 任务，拾取可用槽位数个任务推进。"""
    run_download_worker = _get_worker()
    tick = 0

    while True:
        try:
            # 每 30 秒执行一次 stuck-pending 恢复
            tick += 1
            if tick % 30 == 0:
                await _recover_stuck_pending()

            slots = _free_slots()
            if slots <= 0:
                await asyncio.sleep(1)
                continue

            async with AsyncSessionLocal() as db:
                stmt = (
                    select(DownloadTask)
                    .where(DownloadTask.status == "queued")
                    .order_by(DownloadTask.created_at.asc())
                    .limit(slots)
                )
                tasks = (await db.execute(stmt)).scalars().all()

                for task in tasks:
                    task.status = "pending"
                    await db.commit()

                    # 保存强引用，防止 task 对象被 GC
                    t = asyncio.create_task(
                        run_download_worker(task.id),
                        name=f"worker-{task.id}",
                    )
                    _worker_tasks.add(t)
                    # 完成后自动从集合移除，避免内存泄漏
                    t.add_done_callback(_worker_tasks.discard)

        except Exception as e:
            logger.exception(f"scheduler_loop error: {e}")
        await asyncio.sleep(1)
