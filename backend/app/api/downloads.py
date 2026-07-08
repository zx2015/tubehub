"""/api/downloads 路由 (极简自愈版)

时序：
1. POST 时使用 ScraperService 同步获取真实元数据 (含 title, youtube_id)
2. 提前下载缩略图并落盘，免去后期下载延迟
3. 以 queued 状态完整入库
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
)

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.post("/check", response_model=DownloadCheckResponse)
async def check_download(
    req: DownloadCheckRequest,
    db: AsyncSession = Depends(get_db),
):
    """前置探测接口：
    - 快速判断视频是否已在库中
    - 告知前端视频标题及是否是歌单，用于展示防重弹窗
    """
    from app.services.scraper import ScraperService
    url_str = str(req.url)

    # 用 flat=True 快速探测（如果是歌单）
    try:
        info = await ScraperService.fetch_metadata(url_str, flat=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败: {str(e)}")

    is_playlist = info.get("_type") == "playlist"
    youtube_id = info.get("id")
    title = info.get("title")

    # 如果是单视频，且库中已存在
    existing_video = None
    if not is_playlist and youtube_id:
        stmt = select(Video).where(Video.youtube_id == youtube_id)
        video = (await db.execute(stmt)).scalar_one_or_none()
        if video:
            existing_video = ExistingVideoInfo(
                id=video.id,
                title=video.title,
                quality_label=video.quality_label,
                file_size=video.file_size or 0,
                last_position=video.last_position,
            )

    return DownloadCheckResponse(
        conflict=existing_video is not None,
        youtube_id=youtube_id,
        title=title,
        duration=info.get("duration"),
        is_playlist=is_playlist,
        playlist_entries=info.get("entries") if is_playlist else None,
        existing_video=existing_video,
    )


@router.post("", response_model=list[DownloadTaskRead], status_code=201)
async def create_download(
    req: DownloadCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """新增下载任务 (v2 极简代理版)"""
    from app.services.scraper import ScraperService
    from app.services.thumbnail import download_thumbnail

    url_str = str(req.url)

    # 1. 前置拉取完整元数据 (不传代理，自动由环境变量 HTTP_PROXY 穿透)
    try:
        info = await ScraperService.fetch_metadata(url_str, flat=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败: {str(e)}")

    created_tasks: list[DownloadTask] = []

    # 2. 区分单视频与歌单
    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        for entry in entries:
            if not entry:
                continue
            entry_id = entry.get("id")
            entry_url = entry.get("webpage_url") or entry.get("url") or url_str
            entry_title = entry.get("title") or f"Unknown - {entry_id}"

            # 提前下载缩略图（由本地环境变量代理自动捕获）
            if entry_id:
                try:
                    await download_thumbnail(entry_id)
                except Exception as e:
                    logger.warning(f"提前下载歌单缩略图失败 ({entry_id}): {e}")

            task = DownloadTask(
                url=entry_url,
                youtube_id=entry_id,
                title=entry_title,
                format_type=req.format_type,
                quality=req.quality,
                status="queued",
                progress=0.0,
                retry_count=0,
                max_retries=3,
                created_at=datetime.utcnow(),
            )
            db.add(task)
            created_tasks.append(task)
    else:
        # 单视频
        video_id = info.get("id")
        video_title = info.get("title") or "Untitled"

        # 提前下载缩略图
        if video_id:
            try:
                await download_thumbnail(video_id)
            except Exception as e:
                logger.warning(f"提前下载缩略图失败 ({video_id}): {e}")

        task = DownloadTask(
            url=url_str,
            youtube_id=video_id,
            title=video_title,
            format_type=req.format_type,
            quality=req.quality,
            status="queued",
            progress=0.0,
            retry_count=0,
            max_retries=3,
            created_at=datetime.utcnow(),
        )
        db.add(task)
        created_tasks.append(task)

    if not created_tasks:
        raise HTTPException(status_code=400, detail="未能解析到任何可下载的视频")

    await db.commit()
    for t in created_tasks:
        await db.refresh(t)

    logger.info(f"Created {len(created_tasks)} download task(s) (queued) with full metadata")
    return [DownloadTaskRead.model_validate(t) for t in created_tasks]


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


@router.get("/{task_id}", response_model=DownloadTaskRead)
async def get_download(task_id: int, db: AsyncSession = Depends(get_db)):
    """获取任务详情。"""
    task = await db.get(DownloadTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return DownloadTaskRead.model_validate(task)


@router.delete("/{task_id}", status_code=204)
async def delete_download(task_id: int, db: AsyncSession = Depends(get_db)):
    """取消或物理删除下载任务：
    - 若任务处于进行中状态，调用取消逻辑
    - 若任务已处于终态，调用物理删除逻辑清理流水历史
    """
    from app.services.downloader import cancel_running_task, delete_download_task

    task = await db.get(DownloadTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status in ("downloading", "merging", "queued", "pending"):
        ok = await cancel_running_task(task_id)
        if not ok:
            raise HTTPException(status_code=500, detail="取消失败")
    else:
        ok = await delete_download_task(task_id)
        if not ok:
            raise HTTPException(status_code=500, detail="删除记录失败")


@router.post("/{task_id}/retry", response_model=DownloadTaskRead)
async def retry_download(task_id: int, db: AsyncSession = Depends(get_db)):
    """手动重试任务"""
    from app.services.downloader import reset_task_for_manual_retry

    ok = await reset_task_for_manual_retry(task_id)
    if not ok:
        raise HTTPException(status_code=400, detail="当前任务状态不满足重试条件")

    task = await db.get(DownloadTask, task_id)
    return DownloadTaskRead.model_validate(task)


@router.get("/{task_id}/stream")
async def stream_progress(task_id: int, db: AsyncSession = Depends(get_db)):
    """SSE 实时进度推送：每秒轮询一次。"""
    async def event_generator():
        task = await db.get(DownloadTask, task_id)
        if not task:
            yield "event: error\ndata: {\"detail\": \"任务不存在\"}\n\n"
            return

        first_payload = DownloadTaskRead.model_validate(task).model_dump_json()
        yield f"event: progress\ndata: {first_payload}\n\n"

        while True:
            await asyncio.sleep(1.0)
            task = await db.get(DownloadTask, task_id)
            if not task:
                yield "event: error\ndata: {\"detail\": \"任务已被删除\"}\n\n"
                return

            current_state = task.status
            payload = DownloadTaskRead.model_validate(task).model_dump_json()
            yield f"event: progress\ndata: {payload}\n\n"

            if current_state in ("ready", "failed", "cancelled"):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
