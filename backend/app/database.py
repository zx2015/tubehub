import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from .models import Base

# 确保 data 目录存在，避免首次启动建库失败
os.makedirs("data", exist_ok=True)

DATABASE_URL = "sqlite+aiosqlite:///./data/tubehub.db"
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    """启动时建表 + 启用外键约束"""
    async with engine.begin() as conn:
        # 关键：SQLite 必须在每次连接时启用外键，否则 CASCADE 不生效
        await conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
        await conn.run_sync(Base.metadata.create_all)