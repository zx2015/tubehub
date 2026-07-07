"""FastAPI 依赖注入

- get_db: 每请求一个 AsyncSession，结束后自动关闭
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from .database import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """每个请求一个会话；yield 模式下异常也会自动 close。"""
    async with AsyncSessionLocal() as db:
        yield db
