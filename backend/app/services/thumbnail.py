"""
YouTube 缩略图下载服务

策略优先级（高 → 低）：
  1. yt-dlp 返回的最佳质量 URL（可能是 maxresdefault 1080p）
  2. img.youtube.com 降级链：hqdefault → mqdefault → default
  3. 本地占位图

HTTP_PROXY 环境变量由 httpx.AsyncClient 自动隐式捕获，无需手动传参。
"""
import logging
import os
import httpx

logger = logging.getLogger(__name__)

THUMBNAIL_DIR = "data/thumbnails"
SIZES_TRY_ORDER = ["maxresdefault", "hqdefault", "mqdefault", "default"]
PLACEHOLDER = "static/placeholder-thumbnail.jpg"
MIN_VALID_SIZE = 1024
_REQUEST_TIMEOUT = 15.0


async def _fetch_url(url: str) -> bytes | None:
    """下载单个 URL，返回内容字节；失败或内容过小返回 None。"""
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
        if resp.status_code == 200 and len(resp.content) > MIN_VALID_SIZE:
            return resp.content
        logger.warning("Thumbnail URL invalid: status=%s size=%d url=%s",
                       resp.status_code, len(resp.content), url)
    except Exception as exc:
        logger.warning("Thumbnail fetch failed: %s url=%s", exc, url)
    return None


async def download_thumbnail(video_id: str, best_url: str | None = None) -> str:
    """下载 YouTube 缩略图到本地缓存，返回本地路径。

    Args:
        video_id:  YouTube 视频 ID（11 位）
        best_url:  yt-dlp 提供的最佳质量缩略图 URL（可选），优先使用
    """
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    save_path = os.path.join(THUMBNAIL_DIR, f"{video_id}.jpg")

    # 已缓存直接返回
    if os.path.exists(save_path):
        return save_path

    # 1. 优先使用 yt-dlp 提供的最佳 URL（通常是 maxresdefault 或 hq720）
    if best_url:
        content = await _fetch_url(best_url)
        if content:
            with open(save_path, "wb") as fp:
                fp.write(content)
            logger.info("Thumbnail saved via best_url: %s (%d bytes)", video_id, len(content))
            return save_path
        logger.warning("best_url failed for %s, falling back to img.youtube.com", video_id)

    # 2. 降级链：img.youtube.com 固定尺寸
    for size in SIZES_TRY_ORDER:
        url = f"https://img.youtube.com/vi/{video_id}/{size}.jpg"
        content = await _fetch_url(url)
        if content:
            with open(save_path, "wb") as fp:
                fp.write(content)
            logger.info("Thumbnail saved: %s (%s, %d bytes)", video_id, size, len(content))
            return save_path

    # 3. 全部失败：返回占位图
    logger.error("All thumbnail sources failed for %s", video_id)
    return PLACEHOLDER
