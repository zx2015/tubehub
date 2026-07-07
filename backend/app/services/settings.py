import json
import os
from datetime import datetime
from sqlalchemy import select
from ..database import AsyncSessionLocal
from ..models import SystemSetting

COOKIES_FILE_PATH = "data/cookies.txt"


class SettingsService:
    @staticmethod
    async def get_proxy() -> dict:
        """获取代理配置，若不存在返回默认禁用配置"""
        async with AsyncSessionLocal() as db:
            setting = await db.get(SystemSetting, "ytdlp_proxy")
            if not setting:
                return {"enabled": False, "scheme": "http", "host": "", "port": 7890}
            return json.loads(setting.value)

    @staticmethod
    async def set_proxy(proxy_cfg: dict) -> None:
        """保存代理配置"""
        async with AsyncSessionLocal() as db:
            setting = await db.get(SystemSetting, "ytdlp_proxy")
            val = json.dumps(proxy_cfg)
            if not setting:
                db.add(SystemSetting(key="ytdlp_proxy", value=val))
            else:
                setting.value = val
                setting.updated_at = datetime.utcnow()
            await db.commit()

    @staticmethod
    async def get_cookies_status() -> dict:
        """获取 Cookie 文件状态"""
        has_file = os.path.exists(COOKIES_FILE_PATH)
        mtime = None
        size = None
        if has_file:
            stat = os.stat(COOKIES_FILE_PATH)
            mtime = datetime.fromtimestamp(stat.st_mtime)
            size = stat.st_size
        return {"has_cookie": has_file, "updated_at": mtime, "file_size": size}

    @staticmethod
    async def set_cookies(content: str) -> None:
        """上传并保存 Cookie（存 DB + 落盘）"""
        # 1. 写入本地供 yt-dlp 快速调用
        os.makedirs("data", exist_ok=True)
        with open(COOKIES_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(content)

        # 2. 存数据库防丢失（多机或重建时可恢复）
        async with AsyncSessionLocal() as db:
            setting = await db.get(SystemSetting, "ytdlp_cookies")
            if not setting:
                db.add(SystemSetting(key="ytdlp_cookies", value=content))
            else:
                setting.value = content
                setting.updated_at = datetime.utcnow()
            await db.commit()

    @staticmethod
    async def clear_cookies() -> None:
        """清理 Cookie"""
        if os.path.exists(COOKIES_FILE_PATH):
            os.remove(COOKIES_FILE_PATH)
        async with AsyncSessionLocal() as db:
            setting = await db.get(SystemSetting, "ytdlp_cookies")
            if setting:
                await db.delete(setting)
                await db.commit()
