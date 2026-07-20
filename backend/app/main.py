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
    """启动时将 DB 中保存的 cookies 同步到本地文件，并设为只读防止 yt-dlp 覆写。"""
    cookies_path = "data/cookies.txt"
    try:
        async with AsyncSessionLocal() as db:
            setting = await db.get(SystemSetting, "ytdlp_cookies")
            db_content: str = setting.value if setting else ""

        if not db_content.strip():
            logger.debug("No cookies in DB, skipping restore")
            return

        os.makedirs("data", exist_ok=True)

        if os.path.exists(cookies_path):
            os.chmod(cookies_path, 0o644)

        with open(cookies_path, "w", encoding="utf-8") as f:
            f.write(db_content)

        os.chmod(cookies_path, 0o444)

        logger.info(
            "cookies.txt restored from DB and set read-only ({} bytes)",
            len(db_content),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to restore cookies from DB: %s", e)


async def _backfill_video_metadata() -> None:
    """启动时用 ffprobe 补全历史视频的 duration/width/height。

    仅处理 duration IS NULL 且文件存在的记录，避免重复执行影响性能。
    """
    import subprocess, json as _json
    from sqlalchemy import select
    from .models import Video

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Video).where(
                    Video.duration.is_(None),
                    Video.file_path.isnot(None),
                    Video.file_path != "",
                )
            )
            videos = result.scalars().all()

        if not videos:
            return

        logger.info("backfill_video_metadata: %d videos need duration fill", len(videos))
        updated = 0

        for video in videos:
            fp = os.path.abspath(video.file_path) if video.file_path else None
            if not fp or not os.path.exists(fp):
                continue
            try:
                proc = subprocess.run(
                    [
                        "ffprobe", "-v", "quiet",
                        "-print_format", "json",
                        "-show_format", "-show_streams",
                        fp,
                    ],
                    capture_output=True, text=True, timeout=15,
                )
                if proc.returncode != 0:
                    continue
                info = _json.loads(proc.stdout)

                duration = None
                width = None
                height = None

                fmt = info.get("format", {})
                if fmt.get("duration"):
                    try:
                        duration = int(float(fmt["duration"]))
                    except (ValueError, TypeError):
                        pass

                for stream in info.get("streams", []):
                    if stream.get("codec_type") == "video":
                        width = stream.get("width")
                        height = stream.get("height")
                        # fallback duration from stream
                        if duration is None and stream.get("duration"):
                            try:
                                duration = int(float(stream["duration"]))
                            except (ValueError, TypeError):
                                pass
                        break

                if duration is not None or width is not None:
                    async with AsyncSessionLocal() as db:
                        v = await db.get(Video, video.id)
                        if v:
                            if duration is not None:
                                v.duration = duration
                            if width is not None:
                                v.width = width
                            if height is not None:
                                v.height = height
                            await db.commit()
                    updated += 1

            except Exception as e:  # noqa: BLE001
                logger.debug("backfill failed for video %s: %s", video.id, e)

        logger.info("backfill_video_metadata: updated %d/%d videos", updated, len(videos))

    except Exception as e:  # noqa: BLE001
        logger.warning("backfill_video_metadata error: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan 钩子。"""
    await init_db()
    for d in ("data/thumbnails", "data/videos", "logs", "static"):
        os.makedirs(d, exist_ok=True)
    logger.info("TubeHub initialized (db, dirs ready)")

    # 启动时从 DB 恢复 cookies 文件（防止容器重建后文件丢失）
    await _restore_cookies_from_db()

    # 启动时补全历史视频的 duration/width/height（异步后台，不阻塞启动）
    asyncio.create_task(_backfill_video_metadata(), name="backfill_video_metadata")

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
