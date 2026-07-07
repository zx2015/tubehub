import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db
import os

@pytest.mark.asyncio
async def test_health_api():
    """GET /api/health 必须返回 200 且包含 status 字段。"""
    # 显式初始化测试用 DB (内存或独立测试文件)
    await init_db()
    
    # 使用 ASGITransport 绕过 httpx lifespan 机制，直接将 request 投递给 app
    transport = ASGITransport(app=app, raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/health")
        print("Response:", r.status_code, r.text)
        assert r.status_code == 200
        assert "status" in r.json()
