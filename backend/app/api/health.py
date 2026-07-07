"""/api/health 健康检查端点

复刻自 docs/design/07-operations.md §7.2.1
"""
from fastapi import APIRouter
from sqlalchemy import text

from ..database import AsyncSessionLocal

router = APIRouter()


@router.get("/api/health")
async def health():
    """健康检查：DB 可达、FFmpeg 可用、磁盘空间"""
    checks: dict = {}

    # 1. 数据库可达
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["database"] = f"fail: {e}"

    # 2. FFmpeg 可用
    import shutil
    checks["ffmpeg"] = "ok" if shutil.which("ffmpeg") else "missing"

    # 3. 磁盘空间
    try:
        import os
        data_dir = "data"
        if not os.path.isdir(data_dir):
            os.makedirs(data_dir, exist_ok=True)
        usage = shutil.disk_usage(data_dir)
        checks["disk_free_gb"] = round(usage.free / 1024 ** 3, 2)
    except Exception as e:  # noqa: BLE001
        checks["disk_free_gb"] = f"fail: {e}"

    status = "ok" if all(
        v == "ok" or (isinstance(v, (int, float)) and v > 5)
        for v in checks.values()
    ) else "degraded"

    return {"status": status, **checks}
