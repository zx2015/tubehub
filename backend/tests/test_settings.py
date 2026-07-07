import pytest
import os
import tempfile
from app.services.settings import SettingsService, COOKIES_FILE_PATH

@pytest.mark.asyncio
async def test_set_and_get_proxy():
    proxy_cfg = {"enabled": True, "scheme": "socks5", "host": "127.0.0.1", "port": 1080}
    await SettingsService.set_proxy(proxy_cfg)
    loaded = await SettingsService.get_proxy()
    assert loaded["scheme"] == "socks5"
    assert loaded["port"] == 1080

@pytest.mark.asyncio
async def test_cookies_upload():
    if os.path.exists(COOKIES_FILE_PATH):
        os.remove(COOKIES_FILE_PATH)
    await SettingsService.set_cookies("mock_cookies_content")
    assert os.path.exists(COOKIES_FILE_PATH)
    status = await SettingsService.get_cookies_status()
    assert status["has_cookie"] is True
