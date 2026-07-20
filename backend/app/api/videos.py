"""/api/videos 路由

完整接口集见 docs/design/02-api-design.md §2.1
"""
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.deps import get_db
from app.models import Video, PlayHistory
from app.schemas.video import (
    VideoRead,
    VideoProgressUpdate,
    BatchDeleteRequest,
)

router = APIRouter(prefix="/api/videos", tags=["videos"])


def _resolve_path(path: str) -> str:
    """将相对路径转为绝对路径。

    相对路径以进程 CWD（entrypoint.sh 中设为 /app）为基准解析，
    保证与 thumbnail.py / downloader.py 的 data/ 路径一致。
    绝对路径原样返回。
    """
    if os.path.isabs(path):
        return path
    return os.path.abspath(path)  # 相对于 os.getcwd() = /app


@router.get("", response_model=list[VideoRead])
async def list_videos(
    q: Optional[str] = Query(None, description="标题模糊搜索"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """视频库列表（搜索/排序/分页）。"""
    stmt = select(Video).order_by(Video.created_at.desc())
    if q:
        stmt = stmt.where(Video.title.contains(q))
    stmt = stmt.limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    return [VideoRead.model_validate(v) for v in rows]


@router.get("/{video_id}", response_model=VideoRead)
async def get_video(video_id: int, db: AsyncSession = Depends(get_db)):
    """视频详情，包含 last_position 用于播放进度记忆。"""
    video = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    # 将 PlayHistory 中最新的进度回填到 VideoRead（last_position 展示用）
    history = (await db.execute(
        select(PlayHistory).where(PlayHistory.video_id == video_id)
    )).scalar_one_or_none()
    if history and history.position:
        video.last_position = history.position
        video.last_watched_at = history.last_watched_at

    return VideoRead.model_validate(video)


@router.delete("/{video_id}", status_code=204)
async def delete_video(video_id: int, db: AsyncSession = Depends(get_db)):
    """删除单个视频（含文件 + CASCADE 历史）。"""
    video = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    # 物理文件删除（不存在时不阻塞）
    if video.file_path:
        abs_path = _resolve_path(video.file_path)
        try:
            os.remove(abs_path)
        except FileNotFoundError:
            pass

    await db.execute(delete(PlayHistory).where(PlayHistory.video_id == video_id))
    await db.delete(video)
    await db.commit()
    return None


@router.post("/batch-delete", status_code=204)
async def batch_delete_videos(
    req: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """批量删除视频。"""
    videos = (await db.execute(
        select(Video).where(Video.id.in_(req.ids))
    )).scalars().all()

    for video in videos:
        if video.file_path:
            abs_path = _resolve_path(video.file_path)
            try:
                os.remove(abs_path)
            except FileNotFoundError:
                pass
        await db.execute(delete(PlayHistory).where(PlayHistory.video_id == video.id))
        await db.delete(video)

    await db.commit()
    return None


@router.get("/{video_id}/thumbnail")
async def get_thumbnail(video_id: int, db: AsyncSession = Depends(get_db)):
    """返回本地缩略图，若不存在则返回占位图。"""
    from app.services.thumbnail import THUMBNAIL_DIR, PLACEHOLDER

    video = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()

    candidate = video.thumbnail_path if video else None
    if candidate:
        candidate = _resolve_path(candidate)

    if (not candidate or not os.path.exists(candidate)) and video and video.youtube_id:
        candidate = _resolve_path(os.path.join(THUMBNAIL_DIR, f"{video.youtube_id}.jpg"))

    if candidate and os.path.exists(candidate):
        return FileResponse(candidate, media_type="image/jpeg")

    placeholder = _resolve_path(PLACEHOLDER)
    if os.path.exists(placeholder):
        return FileResponse(placeholder, media_type="image/jpeg")

    raise HTTPException(status_code=404, detail="缩略图不存在")


@router.get("/{video_id}/stream")
async def stream_video(
    video_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """视频流式播放，支持 HTTP Range Request（拖拽进度条 / 断点续播所需）。"""
    video = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")
    if not video.file_path:
        raise HTTPException(
            status_code=404,
            detail="视频文件路径未记录（下载时未能确定输出文件路径，可尝试重新下载）",
        )

    abs_path = _resolve_path(video.file_path)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail=f"视频文件不存在: {video.file_path}")

    file_size = os.path.getsize(abs_path)
    range_header = request.headers.get("range")

    # RFC 5987 编码文件名，支持中文等非 ASCII 字符
    from urllib.parse import quote
    encoded_name = quote(os.path.basename(abs_path))
    content_disposition = f"inline; filename*=UTF-8''{encoded_name}"

    # ── 无 Range 头：整段返回 ──────────────────────────────────────
    if not range_header:
        async def full_stream():
            with open(abs_path, "rb") as f:
                while chunk := f.read(512 * 1024):
                    yield chunk

        return StreamingResponse(
            full_stream(),
            status_code=200,
            media_type="video/mp4",
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Content-Disposition": content_disposition,
            },
        )

    # ── 解析 Range 头：bytes=start-end ────────────────────────────
    try:
        raw = range_header.replace("bytes=", "")
        start_str, end_str = raw.split("-")
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1
    except (ValueError, AttributeError):
        raise HTTPException(status_code=416, detail="Range header 格式错误")

    if start >= file_size or end >= file_size or start > end:
        raise HTTPException(
            status_code=416,
            detail="请求范围超出文件大小",
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    chunk_size = end - start + 1

    async def partial_stream():
        with open(abs_path, "rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                data = f.read(min(512 * 1024, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return StreamingResponse(
        partial_stream(),
        status_code=206,
        media_type="video/mp4",
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(chunk_size),
            "Accept-Ranges": "bytes",
            "Content-Disposition": content_disposition,
        },
    )


@router.patch("/{video_id}/progress")
async def update_progress(
    video_id: int,
    req: VideoProgressUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新播放进度，upsert PlayHistory，≥95% 标记为已看完。"""
    video = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    now = datetime.utcnow()
    progress_percent = (req.position / req.duration * 100) if req.duration > 0 else 0.0
    completed = progress_percent >= 95.0

    # upsert PlayHistory（video_id 有唯一约束，每个视频只保留一条）
    history = (await db.execute(
        select(PlayHistory).where(PlayHistory.video_id == video_id)
    )).scalar_one_or_none()

    if history:
        history.position = req.position
        history.duration = req.duration
        history.progress_percent = progress_percent
        history.completed = completed
        history.last_watched_at = now
        history.watch_count = (history.watch_count or 0) + 1
    else:
        history = PlayHistory(
            video_id=video_id,
            position=req.position,
            duration=req.duration,
            progress_percent=progress_percent,
            completed=completed,
            first_watched_at=now,
            last_watched_at=now,
            watch_count=1,
        )
        db.add(history)

    # 同步 Video.last_position 便于列表页展示进度条
    video.last_position = req.position
    video.last_watched_at = now

    await db.commit()
    return {"video_id": video_id, "position": req.position, "progress_percent": round(progress_percent, 1), "completed": completed}
