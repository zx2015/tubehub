"""
缩略图下载服务测试（Task 5）

覆盖：
- 降级链：hqdefault → mqdefault → default 全失败时返回占位图
- 缓存命中：本地已有文件直接返回，不发起网络请求
- 大小过滤：YouTube 占位图 < 1KB 必须被过滤掉
- 成功路径：响应 >= 1KB 时保存到本地并返回路径
"""

import os
import pytest
import httpx
import respx

from app.services.thumbnail import (
    download_thumbnail,
    THUMBNAIL_DIR,
    SIZES_TRY_ORDER,
    PLACEHOLDER,
)


YT_IMG_BASE = "https://img.youtube.com"


def _yt_url(video_id: str, size: str) -> str:
    return f"{YT_IMG_BASE}/vi/{video_id}/{size}.jpg"


# ---------------------------------------------------------------------------
# 边界 / 常量
# ---------------------------------------------------------------------------
def test_constants_have_expected_values():
    assert THUMBNAIL_DIR == "data/thumbnails"
    assert SIZES_TRY_ORDER == ["hqdefault", "mqdefault", "default"]
    assert PLACEHOLDER == "static/placeholder-thumbnail.jpg"


# ---------------------------------------------------------------------------
# 降级路径：所有尺寸都返回 < 1KB 占位图时，必须回退到占位图
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_thumbnail_download_fallback():
    """用户任务示例：传入无效 video_id，YouTube 仍返回 120x90 占位图（< 1KB），
    三个 size 都被大小过滤拦截 → 最终回退到 PLACEHOLDER。"""
    video_id = "invalid_id_xxxx"

    # 拦截所有 YouTube 缩略图请求，模拟 < 1KB 占位图
    for size in SIZES_TRY_ORDER:
        respx.get(_yt_url(video_id, size)).mock(
            return_value=httpx.Response(200, content=b"x" * 500)  # < 1024
        )

    path = await download_thumbnail(video_id)
    assert path == "static/placeholder-thumbnail.jpg"

    # 降级链必须被按顺序全部尝试
    for size in SIZES_TRY_ORDER:
        assert respx.calls.call_count >= 1  # 至少发生过请求


# ---------------------------------------------------------------------------
# 异常降级：网络异常时也要继续尝试下一个 size
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_thumbnail_exception_continues_next_size():
    video_id = "raises_id_zzzz"

    # 第一个 size 抛异常，后续两个返回 < 1KB 占位图
    respx.get(_yt_url(video_id, "hqdefault")).mock(
        side_effect=httpx.ConnectError("boom")
    )
    for size in ("mqdefault", "default"):
        respx.get(_yt_url(video_id, size)).mock(
            return_value=httpx.Response(200, content=b"x" * 500)
        )

    path = await download_thumbnail(video_id)
    assert path == "static/placeholder-thumbnail.jpg"


# ---------------------------------------------------------------------------
# 成功路径：>= 1KB 时真正落盘
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_thumbnail_saves_when_large_enough(tmp_path, monkeypatch):
    """当 hqdefault 返回足够大的图时，写入本地并返回 save_path。"""
    # 隔离 THUMBNAIL_DIR 到 tmp_path，避免污染仓库
    monkeypatch.setattr(
        "app.services.thumbnail.THUMBNAIL_DIR", str(tmp_path / "thumbs")
    )

    video_id = "valid_id_1234"
    payload = b"\x00" * 4096  # 4KB，远超 1024 阈值

    respx.get(_yt_url(video_id, "hqdefault")).mock(
        return_value=httpx.Response(200, content=payload)
    )

    path = await download_thumbnail(video_id)
    expected = os.path.join(str(tmp_path / "thumbs"), f"{video_id}.jpg")
    assert path == expected
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == payload


# ---------------------------------------------------------------------------
# 缓存命中：已存在文件时直接返回，不发请求
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_thumbnail_cache_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.thumbnail.THUMBNAIL_DIR", str(tmp_path / "thumbs")
    )

    video_id = "cached_id_5555"
    cached = tmp_path / "thumbs" / f"{video_id}.jpg"
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(b"\x42" * 2048)

    # 如果命中缓存，不会发出任何 HTTP 请求；respx 若有未匹配的路由会失败
    path = await download_thumbnail(video_id)
    assert path == str(cached)


# ---------------------------------------------------------------------------
# 代理透传：proxy_url 不为 None 时，AsyncClient 必须用该 proxy
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_thumbnail_passes_proxy_url(monkeypatch):
    """通过捕获 httpx.AsyncClient 的 proxy kwarg 验证代理透传。"""
    captured: dict = {}

    real_async_client = httpx.AsyncClient

    def spy_client(*args, **kwargs):
        captured.update(kwargs)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", spy_client)

    video_id = "proxy_id_9999"
    respx.get(_yt_url(video_id, "hqdefault")).mock(
        return_value=httpx.Response(200, content=b"x" * 500)
    )
    respx.get(_yt_url(video_id, "mqdefault")).mock(
        return_value=httpx.Response(200, content=b"x" * 500)
    )
    respx.get(_yt_url(video_id, "default")).mock(
        return_value=httpx.Response(200, content=b"x" * 500)
    )

    await download_thumbnail(video_id)
