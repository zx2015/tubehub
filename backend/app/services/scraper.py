"""
scraper.py — v3.0 双 select 严格模式

使用 yt-dlp 完整 extract_info 拉取真实 formats 列表。
"""
import asyncio
import logging
from typing import Any

import yt_dlp

logger = logging.getLogger(__name__)


def _build_ydl_opts(download: bool = False) -> dict:
    """构造 yt-dlp 探测选项：不下载、读取真实全部 formats。"""
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,  # 严格只探测不下载
        # 绕过 YouTube PO-Token 校验
        "extractor_args": {
            "youtube": {
                "player_client": ["tv", "android", "web"],
            }
        },
    }


async def _run_in_executor(sync_fn) -> Any:
    """在默认线程池中执行同步阻塞的 yt-dlp 调用，避免阻塞事件循环。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, sync_fn)


def _extract(url: str) -> dict:
    """同步阻塞调用 yt-dlp extract_info。"""
    with yt_dlp.YoutubeDL(_build_ydl_opts(download=False)) as ydl:
        return ydl.extract_info(url, download=False)


def _filter_video_formats(formats: list[dict]) -> list[dict]:
    """筛选出所有视频轨（vcodec != none）。"""
    return [f for f in formats if f.get("vcodec") and f.get("vcodec") != "none"]


def _filter_audio_formats(formats: list[dict]) -> list[dict]:
    """筛选出所有音频轨（acodec != none）。"""
    return [f for f in formats if f.get("acodec") and f.get("acodec") != "none"]


def _format_label(f: dict) -> str:
    """生成人类可读的格式描述。"""
    parts = []
    if f.get("height"):
        parts.append(f"{f['height']}p")
    if f.get("vcodec") and f["vcodec"] != "none":
        parts.append(f["vcodec"].split(".")[0])
    if f.get("fps") and f["fps"] >= 50:
        parts.append(f"{int(f['fps'])}fps")
    if f.get("tbr"):
        parts.append(f"~{int(f['tbr'])}kbps")
    if f.get("filesize") or f.get("filesize_approx"):
        size = f.get("filesize") or f.get("filesize_approx")
        if size > 1024 * 1024:
            parts.append(f"{size // (1024*1024)}MB")
        elif size:
            parts.append(f"{size // 1024}KB")
    if f.get("ext"):
        parts.append(f.get("ext"))
    if f.get("format_note"):
        note = f["format_note"]
        if note and note not in parts:
            parts.append(note)
    return " · ".join(str(p) for p in parts) if parts else f.get("format", "?")


class ScraperService:
    """对外提供视频元信息与 formats 探测服务。"""

    @staticmethod
    async def fetch_metadata(url: str) -> dict:
        """完整拉取元信息（与 fetch_formats 共享底层，但保留向后兼容）。"""
        try:
            logger.info(f"Scraper: fetching metadata for {url}")
            return await _run_in_executor(lambda: _extract(url))
        except Exception as e:
            logger.error(f"Scraper: failed for {url}: {e}")
            raise RuntimeError(f"解析视频信息失败: {e}")

    @staticmethod
    async def fetch_video_formats(url: str) -> dict:
        """
        v3.0 探测：返回 {title, youtube_id, duration, video_formats[], audio_formats[]}
        每个 format 项含：{id, label, ext, height/abr, vcodec/acodec, filesize, tbr}
        """
        try:
            logger.info(f"Scraper: v3.0 fetch_video_formats for {url}")
            info = await _run_in_executor(lambda: _extract(url))
        except Exception as e:
            logger.error(f"Scraper: failed for {url}: {e}")
            raise RuntimeError(f"解析视频信息失败: {e}")

        # 歌单：取首条 entry
        if info.get("_type") == "playlist":
            entries = info.get("entries") or []
            if not entries:
                raise RuntimeError("歌单为空或无法访问")
            info = entries[0]

        formats = info.get("formats", []) or []
        video_raw = _filter_video_formats(formats)
        audio_raw = _filter_audio_formats(formats)

        # 构造选项列表
        video_options = [
            {
                "id": f["format_id"],
                "label": f"{_format_label(f)} [{f['format_id']}]",
                "ext": f.get("ext"),
                "height": f.get("height"),
                "width": f.get("width"),
                "vcodec": f.get("vcodec"),
                "tbr": f.get("tbr"),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
            }
            for f in video_raw
        ]
        audio_options = [
            {
                "id": f["format_id"],
                "label": f"{_format_label(f)} [{f['format_id']}]",
                "ext": f.get("ext"),
                "abr": f.get("abr"),
                "acodec": f.get("acodec"),
                "tbr": f.get("tbr"),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
            }
            for f in audio_raw
        ]

        # 按分辨率降序、按码率降序
        video_options.sort(
            key=lambda x: (x.get("height") or 0, x.get("tbr") or 0), reverse=True
        )
        audio_options.sort(key=lambda x: x.get("abr") or 0, reverse=True)

        return {
            "title": info.get("title"),
            "youtube_id": info.get("id"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader") or info.get("channel"),
            "upload_date": info.get("upload_date"),
            "description": info.get("description"),
            "thumbnail": info.get("thumbnail"),
            "video_formats": video_options,
            "audio_formats": audio_options,
        }
