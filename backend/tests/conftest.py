import pytest
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

@pytest.fixture(autouse=True)
async def setup_database():
    """每个测试前重新建表，使用内存数据库避免污染"""
    from app.models import Base
    from app.database import AsyncSessionLocal, engine

    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield