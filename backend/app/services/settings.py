import os
from datetime import datetime
from loguru import logger
from app.database import AsyncSessionLocal
from app.models import SystemSetting

COOKIES_FILE_PATH = "data/cookies.txt"

# SystemSetting keys
_KEY_COOKIES   = "ytdlp_cookies"
_KEY_MCP_URL   = "mcp_browser_url"
_KEY_MCP_TOKEN = "mcp_browser_token"


async def _get_setting(key: str) -> str | None:
    async with AsyncSessionLocal() as db:
        s = await db.get(SystemSetting, key)
        return s.value if s else None


async def _set_setting(key: str, value: str) -> None:
    async with AsyncSessionLocal() as db:
        s = await db.get(SystemSetting, key)
        if not s:
            db.add(SystemSetting(key=key, value=value))
        else:
            s.value = value
            s.updated_at = datetime.utcnow()
        await db.commit()


async def _del_setting(key: str) -> None:
    async with AsyncSessionLocal() as db:
        s = await db.get(SystemSetting, key)
        if s:
            await db.delete(s)
            await db.commit()


class SettingsService:
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
        """上传并保存 Cookie（存 DB + 落盘 + 设只读防覆写）"""
        # 1. 写入本地供 yt-dlp 快速调用，设只读防止被 yt-dlp 覆写
        os.makedirs("data", exist_ok=True)
        # 先解除只读（如果之前已设置）
        if os.path.exists(COOKIES_FILE_PATH):
            os.chmod(COOKIES_FILE_PATH, 0o644)
        with open(COOKIES_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(COOKIES_FILE_PATH, 0o444)  # 只读，防止 yt-dlp 覆写

        # 2. 存数据库防丢失（多机或重建时可恢复）
        await _set_setting(_KEY_COOKIES, content)

    @staticmethod
    async def clear_cookies() -> None:
        """清理 Cookie"""
        if os.path.exists(COOKIES_FILE_PATH):
            os.chmod(COOKIES_FILE_PATH, 0o644)  # 先解除只读再删除
            os.remove(COOKIES_FILE_PATH)
        await _del_setting(_KEY_COOKIES)

    # ------------------------------------------------------------------
    # MCP Browser 配置
    # ------------------------------------------------------------------

    @staticmethod
    async def get_mcp_config() -> dict:
        """读取 MCP Browser 配置，token 返回时做 mask 处理。"""
        url   = await _get_setting(_KEY_MCP_URL)   or ""
        token = await _get_setting(_KEY_MCP_TOKEN) or ""
        masked = _mask_token(token) if token else ""
        return {
            "url": url,
            "token": masked,
            "enabled": bool(url and token),
        }

    @staticmethod
    async def set_mcp_config(url: str, token: str) -> dict:
        """保存 MCP Browser 配置（token 为空时保留旧 token）。"""
        if url:
            await _set_setting(_KEY_MCP_URL, url.rstrip("/"))
        if token and not _is_masked(token):
            # 前端传来的是真实 token（不是 mask 过的），才更新
            await _set_setting(_KEY_MCP_TOKEN, token)
        return await SettingsService.get_mcp_config()

    @staticmethod
    async def sync_cookies_from_mcp() -> dict:
        """
        从 MCP Browser 同步 YouTube cookies。

        Returns:
            {"success": bool, "message": str, "cookie_count": int|None, "file_size": int|None}
        """
        from app.services.mcp_browser import McpBrowserClient, McpBrowserError

        url   = await _get_setting(_KEY_MCP_URL)   or ""
        token = await _get_setting(_KEY_MCP_TOKEN) or ""
        if not url or not token:
            return {"success": False, "message": "MCP Browser 未配置，请先在设置页填写地址和 Token", "cookie_count": None, "file_size": None}

        try:
            client = McpBrowserClient(base_url=url, auth_token=token)
            netscape = client.fetch_youtube_cookies_netscape()
            await SettingsService.set_cookies(netscape)
            # 统计 cookie 行数
            cookie_lines = [l for l in netscape.splitlines() if l and not l.startswith("#")]
            status = await SettingsService.get_cookies_status()
            logger.info("MCP cookie sync OK: %d cookies, %d bytes", len(cookie_lines), status.get("file_size", 0))
            return {
                "success": True,
                "message": f"已从 MCP Browser 同步 {len(cookie_lines)} 个 cookies",
                "cookie_count": len(cookie_lines),
                "file_size": status.get("file_size"),
            }
        except McpBrowserError as e:
            logger.warning("MCP cookie sync failed: %s", e)
            return {"success": False, "message": f"同步失败: {e}", "cookie_count": None, "file_size": None}
        except Exception as e:
            logger.error("MCP cookie sync unexpected error: %s", e, exc_info=True)
            return {"success": False, "message": f"同步异常: {e}", "cookie_count": None, "file_size": None}


def _mask_token(token: str) -> str:
    """将 token 部分遮掩：保留前4位和后4位，中间替换为 ****。"""
    if len(token) <= 8:
        return "****"
    return f"{token[:4]}****{token[-4:]}"


def _is_masked(token: str) -> bool:
    """判断 token 是否是 mask 过的（不应写回 DB）。"""
    return "****" in token
