import pytest
import os
from app.services.settings import SettingsService, COOKIES_FILE_PATH

@pytest.mark.asyncio
async def test_cookies_upload():
    if os.path.exists(COOKIES_FILE_PATH):
        os.remove(COOKIES_FILE_PATH)
    await SettingsService.set_cookies("mock_cookies_content")
    assert os.path.exists(COOKIES_FILE_PATH)
    status = await SettingsService.get_cookies_status()
    assert status["has_cookie"] is True
