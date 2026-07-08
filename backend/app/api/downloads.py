"""/api/downloads 路由 (MVP 简化版)

完整接口集见 docs/design/02-api-design.md §2.1
本文件: check + create 完整实现；其余端点返回占位 JSON，便于后续增量补全。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.deps import get_db
from app.models import DownloadTask, Video
from app.schemas.download import (
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
    """新增下载任务 (v2 重构版):

    时序流程:
    1. 接收 URL 后，先调用 ScraperService.fetch_metadata 使用 yt-dlp 获取真实元数据 (含 formats, title, youtube_id)
    2. 如果是歌单，扁平解析每一个子视频
    3. 立即调用 thumbnail.download_thumbnail 提前把封面落盘到 data/thumbnails
    4. 携带真实元数据写入数据库 (状态直接为 queued)
    """
    from app.services.scraper import ScraperService
    from app.services.thumbnail import download_thumbnail

    url_str = str(req.url)

    # 1. 调用 ScraperService 提取真实元数据
    # - 默认 (flat=False) 以确保单视频 title/youtube_id 完整
    try:
        info = await ScraperService.fetch_metadata(url_str, flat=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败: {str(e)}")

    # 2. 提取代理配置 (供缩略图下载使用)
    from app.services.settings import SettingsService
    proxy_cfg = await SettingsService.get_proxy()
    proxy_url = (
        f"{proxy_cfg['scheme']}://{proxy_cfg['host']}:{proxy_cfg['port']}"
        if proxy_cfg.get("enabled") else None
    )

    created_tasks: list[DownloadTask] = []

    # 3. 区分单视频与歌单
    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        for entry in entries:
            if not entry:
                continue
            entry_id = entry.get("id")
            entry_url = entry.get("webpage_url") or entry.get("url") or url_str
            entry_title = entry.get("title") or f"Unknown - {entry_id}"

            # 提前下载缩略图
            if entry_id:
                try:
                    await download_thumbnail(entry_id, proxy_url)
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
            created_tasks.app.end(task)
    else:
        # 单视频
        video_id = info.get("id")
        video_title = info.get("title") or "Untitled"

        # 提前下载缩略图
        if video_id:
            try:
                await download_thumbnail(video_id, proxy_url)
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
        created_tasks.app.end(task)

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
    """列出下载任务，支持 status 过滤。"""
    stmt = select(DownloadTask).order_by(DownloadTask.created_at.desc())
    if status:
        stmt = stmt.where(DownloadTask.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return [DownloadTaskRead.model_validate(t) for t in rows]


@router.get("/{task_id}", response_model=DownloadTaskRead)
async def get_download(task_id: int, db: AsyncSession = Depends(get_db)):
    """获取任务详情。"""
    from app.models import DownloadTask
    task = await db.get(DownloadTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return DownloadTaskRead.model_validate(task)


@router.delete("/{task_id}", status_code=204)
async def delete_download(task_id: int, db: AsyncSession = Depends(get_db)):
    """取消或物理删除下载任务：
    - 若任务处于进行中状态（downloading / merging / queued），调用取消逻辑
    - 若任务已处于终态（ready / failed / cancelled），调用物理删除逻辑清理流水历史
    """
    from app.models import DownloadTask
    from app.services.downloader import cancel_running_task, delete_download_task

    task = await db.get(DownloadTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status in ("downloading", "merging", "queued", "pending"):
        # 进行中任务 → 调用协程协作取消
        ok = await cancel_running_task(task_id)
        if not ok:
            raise HTTPException(status_code=500, detail="取消失败")
    else:
        # 已结束状态 → 物理从 DB 删除该纪录流水
        ok = await delete_download_task(task_id)
        if not ok:
            raise HTTPException(status_code=500, detail="删除记录失败")


@router.post("/{task_id}/retry", response_model=DownloadTaskRead)
async def retry_download(task_id: int, db: AsyncSession = Depends(get_db)):
    """手动重载/重试下载失败、或被取消的任务"""
    from app.models import DownloadTask
    from app.services.downloader import reset_task_for_manual_retry

    ok = await reset_task_for_manual_retry(task_id)
    if not ok:
        raise HTTPException(status_code=400, detail="当前任务状态不满足重试条件 (必须为 failed/cancelled)")

    # 重新取回状态已重置为 queued 的 task 并返回
    task = await db.get(DownloadTask, task_id)
    return DownloadTaskRead.model_validate(task)


@router.get("/{task_id}/stream")
async def stream_progress(task_id: int, db: AsyncSession = Depends(get_db)):
    """SSE 实时进度推送：
    - 每 1 秒轮询数据库中对应任务的状态/进度字段
    - 一旦状态变为 ready/failed/cancelled 等终态，推送最终帧并关闭连接
    - 防止客户端 EventSource 因响应格式错误中断
    """
    import asyncio
    import json
    from fastapi.responses import StreamingResponse
    from app.models import DownloadTask

    async def event_generator():
        # 1. 推送首帧（无论状态，立即返回当前快照，避免客户端等待）
        task = await db.get(DownloadTask, task_id)
        if not task:
            yield f"event: error\ndata: {{\"detail\": \"任务不存在\"}}\n\n"
            return

        first_payload = DownloadTaskRead.model_validate(task).model_dump_json()
        yield f"event: progress\ndata: {first_payload}\n\n"

        # 2. 周期轮询直到任务进入终态
        last_state = task.status
        while True:
            await asyncio.sleep(1.0)
            task = await db.get(DownloadTask, task_id)
            if not task:
                yield f"event: error\ndata: {{\"detail\": \"任务已被删除\"}}\n\n"
                return

            # 仅当状态或进度变化时推送（减少带宽）
            current_state = task.status
            payload = DownloadTaskRead.model_validate(task).model_dump_json()
            yield f"event: progress\ndata: {payload}\n\n"

            # 终态：推送一次后立即结束
            if current_state in ("ready", "failed", "cancelled"):
                last_state = current_state
                break

            # 防御：如果任务卡在 queued/pending 超过 60s 也主动断开，避免悬挂连接
            if current_state in ("queued", "pending"):
                # 简单心跳：保持连接存活但不强制断开（让客户端继续接收后续进度）
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # 防止 Nginx 等代理缓冲
            "Connection": "keep-alive",
        },
    )
