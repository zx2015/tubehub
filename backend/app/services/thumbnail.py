"""
YouTube 缩略图下载服务

- 降级链 hqdefault → mqdefault → default
- 已缓存文件直接复用，不发请求
- 响应字节数 < 1024 视为 YouTube 占位图，丢弃并尝试下一个 size
- 全部失败时返回静态占位图路径，由前端兜底渲染
- httpx.AsyncClient 透传 proxy_url，与 yt-dlp 走同一代理

参考：
- docs/design/03-yt-dlp-integration.md §3.4
- docs/requirements/03-library.md §3.1.3
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

# 缩略图本地缓存目录（相对仓库根；data/ 在 .gitignore 中）
THUMBNAIL_DIR = "data/thumbnails"

# 降级链顺序：高质量 → 中质量 → 最低保障
SIZES_TRY_ORDER = ["hqdefault", "mqdefault", "default"]

# 全部失败时的占位图（前端静态资源路径）
PLACEHOLDER = "static/placeholder-thumbnail.jpg"

# YouTube 占位图通常 < 1KB，过滤阈值（字节）
MIN_VALID_SIZE = 1024

# 单次请求超时（秒）
_REQUEST_TIMEOUT = 10.0


async def download_thumbnail(
    video_id: str,
    proxy_url: str | None = None,
) -> str:
    """下载 YouTube 缩略图到本地缓存。

    Args:
        video_id: 11 位 YouTube 视频 ID。
        proxy_url: 可选 SOCKS5/HTTP 代理 URL，透传给 httpx。

    Returns:
        缩略图相对路径：
        - 命中本地缓存或任意 size 成功落盘时：`data/thumbnails/{video_id}.jpg`
        - 全部失败时：`static/placeholder-thumbnail.jpg`
    """
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    save_path = os.path.join(THUMBNAIL_DIR, f"{video_id}.jpg")

    # 1. 已缓存直接返回
    if os.path.exists(save_path):
        return save_path

    # 2. 按降级链尝试下载
    for size in SIZES_TRY_ORDER:
        url = f"https://img.youtube.com/vi/{video_id}/{size}.jpg"
        try:
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=_REQUEST_TIMEOUT,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)

            # 必须 200 且超过最小尺寸阈值（过滤 YouTube 自带的占位灰图）
            if resp.status_code == 200 and len(resp.content) > MIN_VALID_SIZE:
                with open(save_path, "wb") as fp:
                    fp.write(resp.content)
                logger.info(
                    "Thumbnail saved: %s (%s, %d bytes)",
                    video_id, size, len(resp.content),
                )
                return save_path

            logger.warning(
                "Thumbnail %s for %s invalid (status=%s, size=%d)",
                size, video_id, resp.status_code, len(resp.content),
            )
        except Exception as exc:  # noqa: BLE001 — 任何网络/HTTP 异常都吞掉，继续降级
            logger.warning(
                "Thumbnail %s fetch failed for %s: %s", size, video_id, exc,
            )
            continue

    # 3. 全部失败：返回占位图
    logger.error("All thumbnail sizes failed for %s", video_id)
    return PLACEHOLDER
