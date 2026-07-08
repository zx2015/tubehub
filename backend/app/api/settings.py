"""/api/settings 路由 (MVP 完整版)

完整接口集见 docs/design/02-api-design.md §2.1
支持 cookies + proxy GET/POST/DELETE + proxy test 全端点。
"""
import time

import httpx
from fastapi import APIRouter, Body

from app.schemas.settings import (
    CookieStatus,
    ProxyConfig,
    ProxyConfigPublic,
    ProxyTestResponse,
)
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
# Proxy
# ---------------------------------------------------------------------------
def _to_public(cfg: dict) -> ProxyConfigPublic:
    """裁掉 password 字段后返回代理公开视图。"""
    return ProxyConfigPublic(
        enabled=cfg.get("enabled", False),
        scheme=cfg.get("scheme", "http"),
        host=cfg.get("host", ""),
        port=cfg.get("port", 7890),
        username=cfg.get("username", ""),
    )


@router.get("/proxy", response_model=ProxyConfigPublic)
async def get_proxy():
    """获取代理配置（屏蔽 password）。"""
    cfg = await SettingsService.get_proxy()
    return _to_public(cfg)


@router.put("/proxy", response_model=ProxyConfigPublic)
async def save_proxy(req: ProxyConfig):
    """保存代理配置。"""
    cfg = {
        "enabled": req.enabled,
        "scheme": req.scheme,
        "host": req.host,
        "port": req.port,
        "username": req.username,
        "password": req.password,
    }
    await SettingsService.set_proxy(cfg)
    return _to_public(cfg)


@router.post("/proxy/test", response_model=ProxyTestResponse)
async def test_proxy(req: ProxyConfig):
    """测试代理连通性：以 https://www.youtube.com/generate_204 作为探活目标。

    返回 latency_ms / status_code / error
    """
    if not req.host:
        return ProxyTestResponse(ok=False, error="host is empty")

    proxy_url = f"{req.scheme}://{req.host}:{req.port}"
    if req.username:
        # httpx basic auth in URL
        from urllib.parse import quote
        proxy_url = (
            f"{req.scheme}://{quote(req.username)}:{quote(req.password)}"
            f"@{req.host}:{req.port}"
        )

    target = "https://www.youtube.com/generate_204"
    timeout_s = 8.0

    t0 = time.time()
    try:
        async with httpx.AsyncClient(
            proxy=proxy_url, timeout=timeout_s, follow_redirects=False,
        ) as client:
            r = await client.get(target)
        latency = int((time.time() - t0) * 1000)
        ok = 200 <= r.status_code < 400
        return ProxyTestResponse(ok=ok, latency_ms=latency, status_code=r.status_code)
    except Exception as e:  # noqa: BLE001
        latency = int((time.time() - t0) * 1000)
        return ProxyTestResponse(ok=False, latency_ms=latency, error=str(e)[:200])
