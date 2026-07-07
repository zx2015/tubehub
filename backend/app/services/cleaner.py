"""后台清理任务（占位实现，MVP 后实现）

- task_cleaner_loop：清理过期的 download_tasks
- history_cleaner_loop：清理 30 天前的 play_history
- 真正实现见 docs/requirements/05-history.md §5.6
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


async def task_cleaner_loop() -> None:
    """每小时清理一次过期任务（占位实现）。"""
    while True:
        try:
            await asyncio.sleep(3600)
            logger.debug("task_cleaner_loop tick (placeholder)")
        except asyncio.CancelledError:
            logger.info("task_cleaner_loop cancelled")
            raise


async def history_cleaner_loop() -> None:
    """每小时清理一次过期历史（占位实现）。"""
    while True:
        try:
            await asyncio.sleep(3600)
            logger.debug("history_cleaner_loop tick (placeholder)")
        except asyncio.CancelledError:
            logger.info("history_cleaner_loop cancelled")
            raise
