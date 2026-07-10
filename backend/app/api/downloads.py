"""/api/downloads 路由 (v3.0 双 select 严格 list-formats)

时序：
1. POST /api/downloads/check (🔍 检测冲突)
   - 走 ScraperService.fetch_metadata 完整探测，返回真实 video_formats + audio_formats
   - 同时查 DB 命中冲突
2. POST /api/downloads
   - 接收前端双 select 提交的 video_format_id + audio_format_id
   - 走 ScraperService.fetch_metadata 拉取真实元数据
   - 提前下载缩略图
   - 以 queued 状态入库（必带 video_format_id + audio_format_id）
"""
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.deps import get_db
from app.models import DownloadTask, Video
from app.schemas.download import (
    DownloadCheckRequest,
    DownloadCheckResponse,
    DownloadCreateRequest,
    DownloadTaskRead,
    ExistingVideoInfo,
    VideoFormatOption,
)

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


# ----------------------------------------------------------------------
# 工具：从 Scraper 探测结果中转换 VideoFormatOption
# ----------------------------------------------------------------------
def _to_video_format_option(f: dict) -> VideoFormatOption:
    return VideoFormatOption(
        id=str(f.get("id")),
        label=f.get("label", f.get("id", "?")),
        ext=f.get("ext"),
        height=f.get("height"),
        width=f.get("width"),
        vcodec=f.get("vcodec"),
        abr=f.get("abr"),
        acodec=f.get("acodec"),
        tbr=f.get("tbr"),
        filesize=f.get("filesize"),
    )


# ----------------------------------------------------------------------
# POST /api/downloads/check  🔍 检测冲突 (v3.0)
# ----------------------------------------------------------------------
@router.post("/check", response_model=DownloadCheckResponse)
async def check_download(
    req: DownloadCheckRequest,
    db: AsyncSession = Depends(get_db),
):
    """v3.0 严格 list-formats 探测：
    - 走完整 extract_info(download=False)
    - 返回 video_formats + audio_formats 供前端下拉
    - 单视频同时查 DB 命中
    - 歌单则返回 entries 列表（歌单模式下双 select 由前端为每个 entry 选）
    """
    from app.services.scraper import ScraperService
    url_str = str(req.url)

    try:
        probe = await ScraperService.fetch_metadata(url_str)
    except Exception as e:
        logger.error(f"check_download: scrape failed for {url_str}: {e}")
        raise HTTPException(status_code=400, detail=f"解析失败: {str(e)}")

    youtube_id = probe.get("youtube_id")
    title = probe.get("title")

    # 查库：单视频是否已存在
    existing_video = None
    if youtube_id:
        stmt = select(Video).where(Video.youtube_id == youtube_id)
        video = (await db.execute(stmt)).scalar_one_or_none()
        if video:
            existing_video = ExistingVideoInfo(
                id=video.id,
                title=video.title,
                video_format_id=video.video_format_id,
                audio_format_id=video.audio_format_id,
                file_size=video.file_size or 0,
                last_position=video.last_position,
            )

    return DownloadCheckResponse(
        conflict=existing_video is not None,
        youtube_id=youtube_id,
        title=title,
        duration=probe.get("duration"),
        uploader=probe.get("uploader"),
        is_playlist=False,  # 简化：v3.0 探测只返回单视频 formats；歌单另行处理
        playlist_entries=None,
        existing_video=existing_video,
        video_formats=[_to_video_format_option(f) for f in probe.get("video_formats", [])],
        audio_formats=[_to_video_format_option(f) for f in probe.get("audio_formats", [])],
    )


# ----------------------------------------------------------------------
# POST /api/downloads  v3.0 双 select 创建任务
# ----------------------------------------------------------------------
@router.post("", response_model=list[DownloadTaskRead], status_code=201)
async def create_download(
    req: DownloadCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    v3.0 严格模式：
    - 必传 video_format_id + audio_format_id（来自前端下拉，list-formats 真实可选）
    - 后端无需关心 /best 兜底（用户不会选到不存在的 ID）
    """
    from app.services.scraper import ScraperService
    from app.services.thumbnail import download_thumbnail

    url_str = str(req.url)
    logger.info(
        f"create_download ENTERED: url={url_str} "
        f"video_format_id={req.video_format_id!r} (type={type(req.video_format_id).__name__}), "
        f"audio_format_id={req.audio_format_id!r} (type={type(req.audio_format_id).__name__}), "
        f"overwrite={req.overwrite}"
    )


    if not req.video_format_id or not req.audio_format_id:
        raise HTTPException(
            status_code=400,
            detail="必须选择视频格式与音频格式 (v3.0 严格 list-formats)",
        )

    # 1. 完整拉取元信息
    try:
        probe = await ScraperService.fetch_metadata(url_str)
        logger.info(
            f"create_download: scrape OK youtube_id={probe.get('youtube_id')} "
            f"title={probe.get('title', '')[:50]!r} "
            f"video_count={len(probe.get('video_formats', []))} "
            f"audio_count={len(probe.get('audio_formats', []))}"
        )

    except Exception as e:
        logger.error(f"create_download: scrape failed for {url_str}: {e}")
        raise HTTPException(status_code=400, detail=f"解析失败: {str(e)}")

    # 2. 校验用户选的两个 format_id 是否在 list-formats 中（严格性保障）
    # format_id 在前端下拉中是字符串，但 request schema 已改为 int（与 model 一致）
    video_ids = {int(f["id"]) for f in probe.get("video_formats", [])}
    audio_ids = {int(f["id"]) for f in probe.get("audio_formats", [])}
    logger.info(
        f"create_download: validation V_id={req.video_format_id} "
        f"A_id={req.audio_format_id} | valid V={sorted(video_ids)} valid A={sorted(audio_ids)}"
    )
    if req.video_format_id not in video_ids:
        logger.error(
            f"create_download: video_format_id {req.video_format_id} 不在 {sorted(video_ids)}"
        )
        raise HTTPException(
            status_code=400,
            detail=f"视频格式 ID {req.video_format_id} 不在可选列表中，请重新选择",
        )
    if req.audio_format_id not in audio_ids:
        logger.error(
            f"create_download: audio_format_id {req.audio_format_id} 不在 {sorted(audio_ids)}"
        )
        raise HTTPException(
            status_code=400,
            detail=f"音频格式 ID {req.audio_format_id} 不在可选列表中，请重新选择",
        )

    video_id = probe.get("youtube_id")
    video_title = probe.get("title") or "Untitled"
    best_thumbnail_url = probe.get("thumbnail")  # yt-dlp 已选出最佳质量 URL

    # 3. 提前下载缩略图（优先使用 yt-dlp 的最佳 URL，其次降级链）
    if video_id:
        try:
            await download_thumbnail(video_id, best_url=best_thumbnail_url)
        except Exception as e:
            logger.warning(f"提前下载缩略图失败 ({video_id}): {e}")

    # 4. 冲突检查（除非 overwrite）
    if video_id and not req.overwrite:
        existing = (await db.execute(
            select(Video).where(Video.youtube_id == video_id)
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"视频已存在 (id={existing.id}, title={existing.title})；如需覆盖请传 overwrite=true",
            )

    # 5. 写库
    task = DownloadTask(
        url=url_str,
        youtube_id=video_id,
        title=video_title,
        video_format_id=int(req.video_format_id),
        audio_format_id=int(req.audio_format_id),
        status="queued",
        progress=0.0,
        retry_count=0,
        max_retries=3,
        created_at=datetime.utcnow(),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    logger.info(
        f"Created v3.0 download task id={task.id} vid={video_id} "
        f"V={req.video_format_id} A={req.audio_format_id}"
    )
    logger.success(
        f"create_download SUCCESS: task_id={task.id} vid={video_id} "
        f"V={task.video_format_id} A={task.audio_format_id} title={video_title[:30]!r} "
        f"url={url_str}"
    )
    return [DownloadTaskRead.model_validate(task)]


# ----------------------------------------------------------------------
# GET /api/downloads  列表
# ----------------------------------------------------------------------
@router.get("", response_model=list[DownloadTaskRead])
async def list_downloads(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """列出所有下载任务。"""
    stmt = select(DownloadTask).order_by(DownloadTask.created_at.desc())
    if status:
        stmt = stmt.where(DownloadTask.status == status)
    tasks = (await db.execute(stmt)).scalars().all()
    return [DownloadTaskRead.model_validate(t) for t in tasks]


# ----------------------------------------------------------------------
# GET /api/downloads/{id}  任务详情
# ----------------------------------------------------------------------
@router.get("/{task_id}", response_model=DownloadTaskRead)
async def get_download(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(DownloadTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return DownloadTaskRead.model_validate(task)


# ----------------------------------------------------------------------
# DELETE /api/downloads/{id}  取消/删除
# ----------------------------------------------------------------------
@router.delete("/{task_id}", status_code=204)
async def delete_download(task_id: int, db: AsyncSession = Depends(get_db)):
    """双向自愈型删除：进行中→取消；已完成→物理删除。"""
    from app.services.downloader import cancel_running_task, delete_download_task
    task = await db.get(DownloadTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status in ("pending", "queued", "downloading", "merging"):
        # 正在运行且有活跃 worker：先取消
        from app.services.scheduler import cancel_events
        if task_id in cancel_events:
            ok = await cancel_running_task(task_id)
            if not ok:
                raise HTTPException(status_code=409, detail="任务取消失败，请稍后重试")
        else:
            # 失联僵尸任务（状态仍在运行态但无 worker）：允许直接删除
            ok = await delete_download_task(task_id, allow_in_progress=True)
            if not ok:
                raise HTTPException(status_code=409, detail="任务删除失败，请稍后重试")
    else:
        ok = await delete_download_task(task_id)
        if not ok:
            raise HTTPException(status_code=409, detail="任务删除失败，请稍后重试")
    return


# ----------------------------------------------------------------------
# POST /api/downloads/{id}/retry  手动重试
# ----------------------------------------------------------------------
@router.post("/{task_id}/retry")
async def retry_download(task_id: int, db: AsyncSession = Depends(get_db)):
    """手动重试：仅 failed/cancelled 状态可重试。"""
    from app.services.downloader import reset_task_for_manual_retry
    task = await db.get(DownloadTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in ("failed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail="当前任务状态不满足重试条件 (必须为 failed/cancelled)",
        )
    await reset_task_for_manual_retry(task_id)
    await db.refresh(task)
    return DownloadTaskRead.model_validate(task)


# ----------------------------------------------------------------------
# GET /api/downloads/{id}/stream  SSE 实时进度推送
# ----------------------------------------------------------------------
@router.get("/{task_id}/stream")
async def stream_progress(task_id: int, db: AsyncSession = Depends(get_db)):
    """SSE 实时推送：每秒轮询任务状态/进度。"""
    from app.database import AsyncSessionLocal
    from app.models import DownloadTask as DT

    TERMINAL_STATUS = {"ready", "failed", "cancelled", "deleted"}

    async def event_generator():
        # 立即推送首帧
        async with AsyncSessionLocal() as session:
            task = await session.get(DT, task_id)
            if task:
                yield _format_event("progress", DownloadTaskRead.model_validate(task).model_dump_json())
            else:
                yield _format_event("error", '{"detail":"任务不存在"}')
                return

        # 1Hz 轮询
        for _ in range(60 * 60):  # 最多 1 小时
            await asyncio.sleep(1)
            async with AsyncSessionLocal() as session:
                task = await session.get(DT, task_id)
                if not task:
                    yield _format_event("error", '{"detail":"任务已被删除"}')
                    return
                payload = DownloadTaskRead.model_validate(task).model_dump_json()
                yield _format_event("progress", payload)
                if task.status in TERMINAL_STATUS:
                    return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _format_event(event: str, data: str) -> str:
    # 注意：前端 EventSource.onmessage 只处理无名事件（无 event: 行）。
    # 保留 event 参数便于扩展，但实际只发 data: 行，让 onmessage 直接接收。
    if event == "error":
        return f"data: {data}\n\n"
    return f"data: {data}\n\n"
