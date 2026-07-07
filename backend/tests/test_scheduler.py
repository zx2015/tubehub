import pytest
import asyncio
from app.services.scheduler import download_semaphore


@pytest.mark.asyncio
async def test_concurrency_slots():
    """调度器全局信号量初始值必须为 2（详见需求 02 §2.6 并发控制）"""
    assert download_semaphore._value == 2
