"""/api/downloads 路由 (MVP 简化版)

完整接口集见 docs/design/02-api-design.md §2.1
本文件: check + create 完整实现；其余端点返回占位 JSON，便于后续增量补全。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..deps import get_db
from ..models import DownloadTask, Video
from ..schemas.download import (
    DownloadCheckRequest,
    DownloadCheckResponse,
    DownloadCreateRequest,
    DownloadTaskRead,
)

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


def _extract_youtube_id(url: str) -> Optional[str]:
    """极简的 youtube_id 抽取，仅用于 MVP 阶段的 check/占位实现。

    不调用 yt_dlp.extract_info，避免测试环境触发网络。
    """
    import re
    patterns = [
        r"(?:v=|/)([0-9A-Za-z_-]{11})(?:[?&#]|$)",
        r"youtu\.be/([0-9A-Za-z_-]{11})",
        r"shorts/([0-9A-Za-z_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


@router.post("/check", response_model=DownloadCheckResponse)
async def check_download(
    req: DownloadCheckRequest,
    db: AsyncSession = Depends(get_db),
):
    """前置 check：检测 URL 是否已在库中（避免重复下载）。

    MVP 阶段仅做 URL 解析 + youtube_id 命中查询；完整的元数据 (duration,
    title, playlist) 解析在 scraper 集成后补全。
    """
    url_str = str(req.url)
    youtube_id = _extract_youtube_id(url_str)

    existing = None
    if youtube_id:
        result = await db.execute(
            select(Video).where(Video.youtube_id == youtube_id)
        )
        v = result.scalar_one_or_none()
        if v:
            existing = {
                "id": v.id,
                "title": v.title,
                "quality_label": v.quality_label,
                "file_size": v.file_size or 0,
                "last_position": v.last_position or 0.0,
            }

    return DownloadCheckResponse(
        conflict=existing is not None,
        youtube_id=youtube_id,
        title=None,
        duration=None,
        is_playlist=False,
        playlist_entries=None,
        existing_video=existing,
    )


@router.post("", response_model=list[DownloadTaskRead], status_code=201)
async def create_download(
    req: DownloadCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """创建下载任务。MVP 单 URL 版，歌单展开留待 scraper 集成阶段。"""
    url_str = str(req.url)
    task = DownloadTask(
        url=url_str,
        youtube_id=_extract_youtube_id(url_str),
        format_type=req.format_type,
        quality=req.quality,
        status="queued",
        progress=0.0,
        retry_count=0,
        max_retries=3,
        created_at=datetime.utcnow(),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return [DownloadTaskRead.model_validate(task)]


@router.get("", response_model=list[DownloadTaskRead])
async def list_downloads(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """列出下载任务，支持 status 过滤。"""
    stmt = select(DownloadTask).order_by(DownloadTask.created_at.desc())
    if status:
        stmt = stmt.where(DownloadTask.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return [DownloadTaskRead.model_validate(t) for t in rows]


@router.get("/{task_id}")
async def get_download(task_id: int):
    """任务详情（占位实现）。"""
    return {"msg": "TODO", "task_id": task_id}


@router.delete("/{task_id}", status_code=204)
async def delete_download(task_id: int):
    """取消/删除任务（占位实现）。"""
    return {"msg": "TODO", "task_id": task_id}


@router.post("/{task_id}/retry")
async def retry_download(task_id: int):
    """手动重试失败任务（占位实现）。"""
    return {"msg": "TODO", "task_id": task_id}


@router.get("/{task_id}/stream")
async def stream_progress(task_id: int):
    """SSE 实时进度推送（占位实现，完整 SSE 接入 SSE_Push 模块后实现）。

    SSE 数据格式见 docs/design/06-error-handling.md §6.4.1
    """
    return {"msg": "TODO", "task_id": task_id}
