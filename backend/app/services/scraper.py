"""Scraper Service (v3.0 严格双 select)"""
import asyncio
import logging
import os
import yt_dlp

logger = logging.getLogger(__name__)


_YDL_PROXY_BLOCK = {
    "youtube": {
        "player_client": ["default", "ios", "android", "tv", "web_safari", "web"],
    }
}


def _base_opts(skip_download: bool = True) -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": skip_download,
        "noplaylist": True,
        "ignoreerrors": False,
        "retries": 3,
        "socket_timeout": 30,
    }


def _video_label(f: dict) -> str:
    """生成人类可读的视频格式 label

    示例: "1080p · avc1 · 86MB · mp4 [137]"
    """
    parts = []
    height = f.get("height")
    fps = f.get("fps")
    if height:
        if fps and int(fps) > 30:
            parts.append(f"{int(height)}p{int(fps)}")
        else:
            parts.append(f"{int(height)}p")
    elif fps:
        parts.append(f"{int(fps)}fps")
    vcodec_short = (f.get("vcodec") or "").split(".")[0]
    if vcodec_short and vcodec_short != "none":
        parts.append(vcodec_short)
    filesize = f.get("filesize") or f.get("filesize_approx")
    if filesize:
        mb = filesize / 1024 / 1024
        parts.append(f"{mb:.0f}MB" if mb >= 1 else f"{filesize/1024:.0f}KB")
    else:
        tbr = f.get("tbr") or 0
        if tbr:
            parts.append(f"{tbr:.0f}kbps")
    ext = f.get("ext") or "?"
    parts.append(ext)
    fid = f.get("format_id")
    return f"{' · '.join(parts)} [{fid}]"


def _audio_label(f: dict) -> str:
    """生成人类可读的音频格式 label

    示例: "opus · webm · 24MB · 123kbps · 48kHz [251]"
    """
    parts = []
    acodec = (f.get("acodec") or "").split(".")[0]
    if acodec and acodec != "none":
        parts.append(acodec)
    ext = f.get("ext") or "?"
    parts.append(ext)
    filesize = f.get("filesize") or f.get("filesize_approx")
    if filesize:
        mb = filesize / 1024 / 1024
        parts.append(f"{mb:.0f}MB" if mb >= 1 else f"{filesize/1024:.0f}KB")
    abr = f.get("abr") or 0
    if abr:
        parts.append(f"{abr:.0f}kbps")
    asr = f.get("asr")
    if asr:
        parts.append(f"{int(asr/1000)}kHz")
    fid = f.get("format_id")
    return f"{' · '.join(parts)} [{fid}]"


def _is_thumbnail(f: dict) -> bool:
    vcodec = f.get("vcodec") or ""
    return vcodec == "images"


def _is_progressive(f: dict) -> bool:
    vcodec = f.get("vcodec") or "none"
    acodec = f.get("acodec") or "none"
    return vcodec != "none" and acodec != "none"


class ScraperService:
    @staticmethod
    async def fetch_metadata(url: str) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, ScraperService._sync_extract_info, url
        )

    @staticmethod
    def _sync_extract_info(url: str) -> dict:
        opts = _base_opts(skip_download=True)
        opts["extractor_args"] = _YDL_PROXY_BLOCK
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError("无法解析 YouTube URL")

        formats = info.get("formats") or []
        video_options = []
        audio_options = []
        for f in formats:
            if _is_thumbnail(f):
                continue
            vcodec = f.get("vcodec") or "none"
            acodec = f.get("acodec") or "none"
            if vcodec != "none" and acodec == "none":
                video_options.append({
                    "id": f.get("format_id"),
                    "label": _video_label(f),
                    "ext": f.get("ext"),
                    "vcodec": vcodec,
                    "height": f.get("height"),
                    "tbr": f.get("tbr"),
                    "filesize": f.get("filesize"),
                })
            elif acodec != "none" and vcodec == "none":
                audio_options.append({
                    "id": f.get("format_id"),
                    "label": _audio_label(f),
                    "ext": f.get("ext"),
                    "acodec": acodec,
                    "abr": f.get("abr"),
                    "asr": f.get("asr"),
                    "filesize": f.get("filesize"),
                })

        return {
            "title": info.get("title"),
            "youtube_id": info.get("id"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "channel": info.get("channel") or info.get("uploader"),
            "video_formats": video_options,
            "audio_formats": audio_options,
        }
