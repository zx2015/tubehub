import pytest
import os
import asyncio

os.environ.setdefault("TUBEHUB_ENV", "test")
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

@pytest.fixture(autouse=True)
async def setup_database(request):
    """每个测试前重新建表，但在 API 测试中跳过以防止 SQLite 并发锁盘"""
    # 如果是 API 测试，直接 yield
    if "test_api" in request.node.nodeid:
        yield
        return

    from app.models import Base
    from app.database import AsyncSessionLocal, engine

    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
