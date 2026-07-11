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
from .database import init_db, AsyncSessionLocal
from .models import SystemSetting
from .services.scheduler import scheduler_loop
from .services.cleaner import task_cleaner_loop
from .utils.logger import logger
from .middleware import register_exception_handlers


async def _restore_cookies_from_db() -> None:
    """启动时将 DB 中保存的 cookies 同步到本地文件。

    场景：容器重建后本地 cookies.txt 丢失或为旧版本，DB 里仍有最新备份。
    策略：若 DB 有记录且比文件内容更新（或文件不存在），以 DB 为准覆盖。
    """
    cookies_path = "data/cookies.txt"
    try:
        async with AsyncSessionLocal() as db:
            setting = await db.get(SystemSetting, "ytdlp_cookies")
            if not setting or not setting.value.strip():
                return  # DB 无记录，无需同步

        db_content = setting.value
        # 读取现有文件内容
        file_content = ""
        if os.path.exists(cookies_path):
            with open(cookies_path, "r", encoding="utf-8") as f:
                file_content = f.read()

        # 文件内容与 DB 不一致时，以 DB 为准覆盖
        if file_content != db_content:
            os.makedirs("data", exist_ok=True)
            with open(cookies_path, "w", encoding="utf-8") as f:
                f.write(db_content)
            logger.info(
                "cookies.txt restored from DB (%d bytes, was %d bytes)",
                len(db_content), len(file_content),
            )
        else:
            logger.debug("cookies.txt is up-to-date with DB")
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to restore cookies from DB: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan 钩子。"""
    await init_db()
    for d in ("data/thumbnails", "data/videos", "logs", "static"):
        os.makedirs(d, exist_ok=True)
    logger.info("TubeHub initialized (db, dirs ready)")

    # 启动时从 DB 恢复 cookies 文件（防止容器重建后文件丢失）
    await _restore_cookies_from_db()

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
import os.path as _osp
STATIC_DIR = _osp.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

# 重要：不要用 app.mount("/")，会拦截所有路径让 React Router 无法接管 SPA 路由
# 只挂载 /assets 子目录用于前端静态资源，根路径与所有 SPA 路由都交给 spa_catchall
if _osp.exists(_osp.join(STATIC_DIR, "assets")):
    app.mount("/assets", StaticFiles(directory=_osp.join(STATIC_DIR, "assets")), name="static-assets")

# SPA 兜底路由：所有未匹配的路径（非 /api/*）都返回前端 index.html
# 让 React Router 在前端接管 /downloads、/settings、/watch/:id 等路径
from fastapi.responses import FileResponse, JSONResponse


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_catchall(full_path: str):
    # API 路由交由 FastAPI 自身的 404 处理
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    # 根目录静态文件直通：favicon.svg / robots.txt / manifest.json 等
    static_file = _osp.join(STATIC_DIR, full_path)
    if full_path and _osp.isfile(static_file):
        return FileResponse(static_file)

    # SPA 兜底：所有其他路径返回 index.html 交由 React Router 接管
    index_path = _osp.join(STATIC_DIR, "index.html")
    if _osp.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"detail": "Frontend index.html not found"})
