"""
scraper.py — 核心元数据提取服务。

职责：
- 在任务入库（POST /api/downloads）前，使用 yt-dlp 快速抓取视频/歌单格式、Title、Thumbnail URL 
- 自适应处理单视频与 Playlists (扁平抓取)
- 自动集成 SettingsService 中的代理和 cookies，保证前置解析安全畅通
"""
import asyncio
from loguru import logger
from app.services.settings import SettingsService
from app.services.downloader import _import_yt_dlp


class ScraperService:
    @staticmethod
    async def fetch_metadata(url: str, flat: bool = False) -> dict:
        """
        同步调用 yt-dlp 提取视频或歌单元数据（不下载）。
        使用 run_in_executor 转移到线程池中运行以防卡死 API 进程。

        参数:
            url: 视频/歌单 URL
            flat: 若 True，使用 extract_flat 模式秒级提取（适用于歌单）。若 False，提取完整元数据。
        """
        loop = asyncio.get_running_loop()

        # 1. 动态获取代理与 cookies 配置
        proxy_cfg = await SettingsService.get_proxy()
        proxy_url = (
            f"{proxy_cfg['scheme']}://{proxy_cfg['host']}:{proxy_cfg['port']}"
            if proxy_cfg.get("enabled") else None
        )
        cookies_status = await SettingsService.get_cookies_status()
        cookies_path = "data/cookies.txt" if cookies_status.get("has_cookie", False) else None

        # 2. 构造 yt-dlp 提取参数
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,
            "proxy": proxy_url,
            "cookiefile": cookies_path,

            # 绕过 PO-Token 安全限制
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv", "android", "web"],
                }
            },
        }
        if flat:
            ydl_opts["extract_flat"] = "in_playlist"  # 歌单快速模式

        yt_dlp = _import_yt_dlp()

        def _sync_extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            logger.info(f"Scraper: fetching metadata for {url} via proxy: {proxy_url or 'Direct'}")
            info = await loop.run_in_executor(None, _sync_extract)
            return info
        except Exception as e:
            logger.error(f"Scraper error for {url}: {e}")
            raise RuntimeError(f"解析视频信息失败: {e}")
