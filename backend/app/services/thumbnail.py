"""
YouTube 缩略图下载服务 (极简自愈版)

- 降级链 hqdefault → mqdefault → default
- 全局代路由系统环境变量 HTTP_PROXY 隐式捕获，httpx.AsyncClient 会自动应用，无需手动传参
"""
import logging
import os
import httpx

logger = logging.getLogger(__name__)

THUMBNAIL_DIR = "data/thumbnails"
SIZES_TRY_ORDER = ["hqdefault", "mqdefault", "default"]
PLACEHOLDER = "static/placeholder-thumbnail.jpg"
MIN_VALID_SIZE = 1024
_REQUEST_TIMEOUT = 10.0


async def download_thumbnail(video_id: str) -> str:
    """下载 YouTube 缩略图到本地缓存。

    由本地环境变量 HTTP_PROXY 自动捕获提供代理。
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
            # httpx.AsyncClient 会全自动、隐式应用系统环境变量中的 HTTP_PROXY / HTTPS_PROXY
            async with httpx.AsyncClient(
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
