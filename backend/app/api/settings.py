"""/api/settings 路由 (极简自愈版)

仅保存 cookies 读写接口。代理现由 .env 环境变量接管。
"""
from fastapi import APIRouter, Body

from app.schemas.settings import CookieStatus, McpConfig, McpSyncResult
from app.services.settings import SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Cookies
# ---------------------------------------------------------------------------
@router.get("/cookies", response_model=CookieStatus)
async def get_cookies():
    """获取 Cookie 状态（仅返回元信息，不返回内容）。"""
    info = await SettingsService.get_cookies_status()
    return CookieStatus(
        has_cookie=info["has_cookie"],
        updated_at=info["updated_at"],
        file_size=info["file_size"],
    )


@router.post("/cookies", response_model=CookieStatus)
async def upload_cookies(content: str = Body(..., media_type="text/plain")):
    """上传 Cookie（直接传原始 Netscape cookie 文件内容）。"""
    await SettingsService.set_cookies(content)
    info = await SettingsService.get_cookies_status()
    return CookieStatus(
        has_cookie=info["has_cookie"],
        updated_at=info["updated_at"],
        file_size=info["file_size"],
    )


@router.delete("/cookies", response_model=CookieStatus)
async def clear_cookies_endpoint():
    """清除 Cookie。"""
    await SettingsService.clear_cookies()
    return CookieStatus(has_cookie=False)


# ---------------------------------------------------------------------------
# MCP Browser 配置
# ---------------------------------------------------------------------------
@router.get("/mcp", response_model=McpConfig)
async def get_mcp_config():
    """获取 MCP Browser 配置（token 已 mask）。"""
    cfg = await SettingsService.get_mcp_config()
    return McpConfig(**cfg)


@router.post("/mcp", response_model=McpConfig)
async def save_mcp_config(body: McpConfig):
    """保存 MCP Browser 地址与 Token。"""
    cfg = await SettingsService.set_mcp_config(url=body.url, token=body.token)
    return McpConfig(**cfg)


@router.post("/mcp/sync", response_model=McpSyncResult)
async def sync_mcp_cookies():
    """立即从 MCP Browser 同步 YouTube cookies。"""
    result = await SettingsService.sync_cookies_from_mcp()
    return McpSyncResult(**result)
