"""
yt-dlp 下载调度器

- 维护全局 Semaphore 限制并发下载数（默认 2）
- 维护 cancel_events 池，提供协作式取消能力
- scheduler_loop 每 1 秒扫描一次 queued 任务，按 FIFO 推进
"""

import asyncio
import logging
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import DownloadTask

logger = logging.getLogger(__name__)

# 全局信号量：限制同时 downloading 的任务数（详见需求 02 §2.6）
download_semaphore = asyncio.Semaphore(2)

# 取消事件池：worker 协程可通过它优雅终止
cancel_events: dict[int, asyncio.Event] = {}


# 延迟导入：避免 scheduler <-> downloader 循环依赖
# scheduler_loop 真正运行前，downloader.py 必然已被 app 加载
def _get_worker():
    from .downloader import run_download_worker
    return run_download_worker


async def scheduler_loop() -> None:
    """每 1 秒检查一次 queued 任务，拾取最多 N 个推进"""
    run_download_worker = _get_worker()

    while True:
        try:
            slots = download_semaphore._value  # 剩余槽位
            if slots <= 0:
                await asyncio.sleep(1)
                continue

            async with AsyncSessionLocal() as db:
                # 按 FIFO 取最早 queued 的任务
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
                    # 启动 worker 协程（不阻塞调度循环）
                    asyncio.create_task(run_download_worker(task.id))

        except Exception as e:
            logger.exception(f"scheduler_loop error: {e}")
        await asyncio.sleep(1)
