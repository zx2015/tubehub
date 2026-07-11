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


def _base_opts(skip_download: bool = True, cookies_path: str | None = None) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": skip_download,
        "noplaylist": True,
        "ignoreerrors": False,
        "retries": 3,
        "socket_timeout": 30,
    }
    if cookies_path and os.path.exists(cookies_path):
        opts["cookiefile"] = cookies_path
    return opts


def _get_cookies_path() -> str | None:
    """从标准位置读取 cookies 文件路径，自动验证有效性。"""
    candidate = "data/cookies.txt"
    if not os.path.exists(candidate):
        return None
    try:
        with open(candidate, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("# "):
                    continue
                if "\t" in line or line.startswith("#HttpOnly_"):
                    return candidate
    except Exception:
        pass
    return None


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
    """缩略图 mhtml 格式"""
    return (f.get("vcodec") or "") == "images"


def _is_progressive(f: dict) -> bool:
    """Progressive 混合轨：双 ID 合并策略下不需要"""
    vcodec = f.get("vcodec") or "none"
    acodec = f.get("acodec") or "none"
    return vcodec != "none" and acodec != "none"


def _is_compatible_video(f: dict) -> bool:
    """严格过滤：仅保留 mp4 + avc1（H.264）视频轨
    优势:1) FFmpeg -c copy 零转码合并
         2) 浏览器/video.js 100% 兼容
         3) 文件最小、合并最快
    """
    ext = f.get("ext") or ""
    vcodec = f.get("vcodec") or ""
    return ext == "mp4" and vcodec.startswith("avc1")


def _is_compatible_audio(f: dict) -> bool:
    """严格过滤：仅保留 m4a + mp4a（AAC）音频轨"""
    ext = f.get("ext") or ""
    acodec = f.get("acodec") or ""
    return ext == "m4a" and acodec.startswith("mp4a")


class ScraperService:
    @staticmethod
    async def fetch_metadata(url: str) -> dict:
        loop = asyncio.get_event_loop()
        cookies_path = _get_cookies_path()
        return await loop.run_in_executor(
            None, ScraperService._sync_extract_info, url, cookies_path
        )

    @staticmethod
    def _sync_extract_info(url: str, cookies_path: str | None = None) -> dict:
        opts = _base_opts(skip_download=True, cookies_path=cookies_path)
        opts["extractor_args"] = _YDL_PROXY_BLOCK
        logger.info(
            "ScraperService: extracting %s (cookies=%s)",
            url, cookies_path or "none",
        )
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError("无法解析 YouTube URL")

        formats = info.get("formats") or []
        logger.info(
            "ScraperService: got %d total formats for %s",
            len(formats), info.get("id"),
        )

        video_options = []
        audio_options = []

        for f in formats:
            if _is_thumbnail(f):
                continue
            vcodec_raw = f.get("vcodec") or "none"
            acodec_raw = f.get("acodec") or "none"
            # 排除 progressive 混合轨
            if vcodec_raw != "none" and acodec_raw != "none":
                continue

            if _is_compatible_video(f):
                video_options.append({
                    "id": f.get("format_id"),
                    "label": _video_label(f),
                    "ext": f.get("ext"),
                    "vcodec": vcodec_raw,
                    "height": f.get("height"),
                    "tbr": f.get("tbr"),
                    "filesize": f.get("filesize"),
                })
            elif _is_compatible_audio(f):
                audio_options.append({
                    "id": f.get("format_id"),
                    "label": _audio_label(f),
                    "ext": f.get("ext"),
                    "acodec": acodec_raw,
                    "abr": f.get("abr"),
                    "asr": f.get("asr"),
                    "filesize": f.get("filesize"),
                })

        # Fallback：严格过滤无结果时，放宽为所有纯视频/纯音频轨
        if not video_options or not audio_options:
            logger.warning(
                "ScraperService: strict filter returned v=%d a=%d, falling back to all tracks",
                len(video_options), len(audio_options),
            )
            video_options_fb = []
            audio_options_fb = []
            for f in formats:
                if _is_thumbnail(f):
                    continue
                vcodec_raw = f.get("vcodec") or "none"
                acodec_raw = f.get("acodec") or "none"
                if vcodec_raw != "none" and acodec_raw != "none":
                    continue  # 仍排除 progressive
                if vcodec_raw != "none" and acodec_raw == "none":
                    video_options_fb.append({
                        "id": f.get("format_id"),
                        "label": _video_label(f),
                        "ext": f.get("ext"),
                        "vcodec": vcodec_raw,
                        "height": f.get("height"),
                        "tbr": f.get("tbr"),
                        "filesize": f.get("filesize"),
                    })
                elif acodec_raw != "none" and vcodec_raw == "none":
                    audio_options_fb.append({
                        "id": f.get("format_id"),
                        "label": _audio_label(f),
                        "ext": f.get("ext"),
                        "acodec": acodec_raw,
                        "abr": f.get("abr"),
                        "asr": f.get("asr"),
                        "filesize": f.get("filesize"),
                    })
            if not video_options:
                video_options = video_options_fb
            if not audio_options:
                audio_options = audio_options_fb

        logger.info(
            "ScraperService: final v=%d a=%d for %s",
            len(video_options), len(audio_options), info.get("id"),
        )

        return {
            "title": info.get("title"),
            "youtube_id": info.get("id"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "channel": info.get("channel") or info.get("uploader"),
            "uploader": info.get("uploader"),
            "video_formats": video_options,
            "audio_formats": audio_options,
        }
