"""/api/history 路由"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.deps import get_db
from app.models import Video, PlayHistory

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
async def list_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """列出最近播放历史（按 last_watched_at 倒序）。"""
    stmt = (
        select(PlayHistory, Video)
        .join(Video, PlayHistory.video_id == Video.id)
        .order_by(PlayHistory.last_watched_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "history_id": h.id,
            "video_id": v.id,
            "title": v.title,
            "thumbnail_path": v.thumbnail_path,
            "position": h.position,
            "duration": h.duration,
            "progress_percent": h.progress_percent,
            "completed": h.completed,
            "first_watched_at": h.first_watched_at.isoformat() if h.first_watched_at else None,
            "last_watched_at": h.last_watched_at.isoformat() if h.last_watched_at else None,
            "watch_count": h.watch_count,
        }
        for h, v in rows
    ]


@router.delete("/{history_id}", status_code=204)
async def delete_history(history_id: int, db: AsyncSession = Depends(get_db)):
    """删除单条历史记录。"""
    history = await db.get(PlayHistory, history_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"History {history_id} not found")
    await db.delete(history)
    await db.commit()
    return None


@router.post("/clear")
async def clear_history(
    before_days: Optional[int] = Query(None, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """清空历史记录。

    - before_days 为空：清空全部
    - before_days=N：仅清空 N 天前的记录
    """
    if before_days is not None:
        cutoff = datetime.utcnow() - timedelta(days=before_days)
        stmt = delete(PlayHistory).where(PlayHistory.last_watched_at < cutoff)
    else:
        stmt = delete(PlayHistory)

    result = await db.execute(stmt)
    await db.commit()
    return {"deleted_count": result.rowcount, "before_days": before_days}
