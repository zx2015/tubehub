import pytest
from sqlalchemy import select
from app.database import init_db, AsyncSessionLocal
from app.models import Video, PlayHistory, DownloadTask
from app.services.downloader import delete_download_task

@pytest.mark.asyncio
async def test_cascade_delete_history():
    await init_db()
    async with AsyncSessionLocal() as db:
        video = Video(youtube_id="test_id_123", title="Test Title", file_path="/mock/path")
        db.add(video)
        await db.commit()
        await db.refresh(video)

        history = PlayHistory(video_id=video.id, position=10.0, duration=100.0)
        db.add(history)
        await db.commit()

        # 删除 video
        await db.delete(video)
        await db.commit()

        # 验证 history 自动级联清理 (CASCADE)
        hist = (await db.execute(select(PlayHistory).where(PlayHistory.video_id == video.id))).scalar_one_or_none()
        assert hist is None


@pytest.mark.asyncio
async def test_delete_zombie_in_progress_task():
    await init_db()
    async with AsyncSessionLocal() as db:
        task = DownloadTask(
            url="https://www.youtube.com/watch?v=test",
            youtube_id="test_dl_001",
            title="zombie task",
            video_format_id=137,
            audio_format_id=140,
            status="merging",
            progress=0.0,
            retry_count=0,
            max_retries=3,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id

    # 默认不允许删除进行中任务
    assert await delete_download_task(task_id) is False
    # 允许僵尸清理模式后应可删除
    assert await delete_download_task(task_id, allow_in_progress=True) is True

    async with AsyncSessionLocal() as db:
        deleted = await db.get(DownloadTask, task_id)
        assert deleted is None