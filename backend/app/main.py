"""TubeHub FastAPI 应用入口

- lifespan: 启动/关闭钩子 (docs/design/00-architecture.md §0.1.2)
- 注册所有 APIRouter
- 注册全局异常处理 (docs/design/06-error-handling.md §6.1)
- 挂载静态目录 (data/thumbnails / 前端构建产物)
"""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import health, downloads, videos, history, settings
from .database import init_db
from .services.scheduler import scheduler_loop
from .services.cleaner import task_cleaner_loop
from .utils.logger import logger
from .middleware import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan 钩子。"""
    await init_db()
    for d in ("data/thumbnails", "data/videos", "logs", "static"):
        os.makedirs(d, exist_ok=True)
    logger.info("TubeHub initialized (db, dirs ready)")

    # 如果是测试环境，不启动真实的后台循环
    if os.getenv("TUBEHUB_ENV") == "test":
        async def dummy_loop():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass
        sched_task = asyncio.create_task(dummy_loop(), name="scheduler_loop")
        clean_task = asyncio.create_task(dummy_loop(), name="task_cleaner_loop")
    else:
        sched_task = asyncio.create_task(scheduler_loop(), name="scheduler_loop")
        clean_task = asyncio.create_task(task_cleaner_loop(), name="task_cleaner_loop")
    logger.info("TubeHub started")
    try:
        yield
    finally:
        sched_task.cancel()
        clean_task.cancel()
        for t in (sched_task, clean_task):
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Background task {t.get_name()} exit: {e}")
        logger.info("TubeHub stopped")


app = FastAPI(title="TubeHub", version="0.1.0", lifespan=lifespan)

# 全局异常处理
register_exception_handlers(app)

# 路由
app.include_router(health.router)
app.include_router(downloads.router)
app.include_router(videos.router)
app.include_router(history.router)
app.include_router(settings.router)

# 静态目录（缩略图占位图、前端构建产物等）
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
