import pytest
from sqlalchemy import select
from app.database import init_db, AsyncSessionLocal
from app.models import Video, PlayHistory

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