"""/api/videos 路由 (MVP 简化版)

完整接口集见 docs/design/02-api-design.md §2.1
本文件: list + delete 完整实现；其余端点返回占位 JSON。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ..deps import get_db
from ..models import Video, PlayHistory
from ..schemas.video import (
    VideoRead,
    VideoProgressUpdate,
    BatchDeleteRequest,
)

router = APIRouter(prefix="/api/videos", tags=["videos"])


@router.get("", response_model=list[VideoRead])
async def list_videos(
    q: Optional[str] = Query(None, description="标题模糊搜索"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """视频库列表（搜索/排序/分页）。MVP 阶段支持 title 模糊匹配。"""
    stmt = select(Video).order_by(Video.created_at.desc())
    if q:
        stmt = stmt.where(Video.title.contains(q))
    stmt = stmt.limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    return [VideoRead.model_validate(v) for v in rows]


@router.get("/{video_id}")
async def get_video(video_id: int):
    """视频详情（占位实现）。"""
    return {"msg": "TODO", "video_id": video_id}


@router.delete("/{video_id}", status_code=204)
async def delete_video(video_id: int, db: AsyncSession = Depends(get_db)):
    """删除单个视频（含文件 + CASCADE 历史）。

    MVP 实现：DB 删除（FileNotFound 时不阻塞 IO 异常处理）。
    物理文件清理与"下载中冲突 (TUBEHUB_FCONFLICT_DELETE)" 在清理模块完成后接入。
    """
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found")
    # 先删历史（外键 ON DELETE CASCADE 也会兜底，但显式删除更清晰）
    await db.execute(delete(PlayHistory).where(PlayHistory.video_id == video_id))
    await db.delete(video)
    await db.commit()
    return None


@router.post("/batch-delete", status_code=204)
async def batch_delete_videos(
    req: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """批量删除（占位实现）。"""
    return {"msg": "TODO", "ids": req.ids}


@router.get("/{video_id}/thumbnail")
async def get_thumbnail(video_id: int):
    """返回本地缩略图（占位实现）。"""
    return {"msg": "TODO", "video_id": video_id}


@router.get("/{video_id}/stream")
async def stream_video(video_id: int):
    """视频流式播放（占位实现，需等 video.js 集成与 Range Request 落地后补全）。"""
    return {"msg": "TODO", "video_id": video_id}


@router.patch("/{video_id}/progress")
async def update_progress(
    video_id: int,
    req: VideoProgressUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新播放进度（占位实现）。

    完整实现：upsert PlayHistory，并按 (position / duration) >= 0.95 标记 completed。
    """
    return {
        "msg": "TODO",
        "video_id": video_id,
        "position": req.position,
        "duration": req.duration,
        "updated_at": datetime.utcnow().isoformat(),
    }
