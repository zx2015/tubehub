"""/api/history 路由 (MVP 简化版)

完整接口集见 docs/design/02-api-design.md §2.1
本文件: list 完整实现；其余端点占位。
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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
async def delete_history(history_id: int):
    """删除单条历史（占位实现）。"""
    return {"msg": "TODO", "history_id": history_id}


@router.post("/clear")
async def clear_history(
    before_days: Optional[int] = Query(None, ge=1, le=365),
):
    """清空历史（可带 before_days 参数；占位实现）。"""
    return {"msg": "TODO", "before_days": before_days}
