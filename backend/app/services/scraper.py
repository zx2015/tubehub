"""Scraper Service (v3.0 严格双 select)"""
import asyncio
import logging
import os
import yt_dlp

logger = logging.getLogger(__name__)


_YDL_PROXY_BLOCK = {
    "youtube": {
        # 不限制 player_client，让 yt-dlp 自动选择
        # android_vr 无需 n-challenge，最稳定；有 cookies 时会优先用认证 client
        "player_client": ["android_vr", "tv", "web", "default"],
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
        # 允许 deno 从 GitHub 下载 EJS challenge solver 脚本
        # yt-dlp 2026.07+ 处理受限视频需要此脚本解决 n-challenge
        "remote_components": ["ejs:github"],
        # 禁止 yt-dlp 更新/覆写 cookies 文件，防止覆盖用户上传的有效 cookies
        "no_cookies_update": True,
    }
    if cookies_path and os.path.exists(cookies_path):
        opts["cookiefile"] = cookies_path
    return opts


def _get_cookies_path() -> str | None:
    """从 DB 实时读取 cookies 写到临时只读文件，防止 yt-dlp 覆写磁盘文件。"""
    import sqlite3, tempfile

    db_path = "data/tubehub.db"
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key='ytdlp_cookies'"
            ).fetchone()
            conn.close()
            if row and row[0].strip():
                content = row[0]
                # 写到临时只读文件，yt-dlp 无法覆写
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8"
                )
                tmp.write(content)
                tmp.close()
                os.chmod(tmp.name, 0o444)
                return tmp.name
        except Exception as e:
            logger.warning("Failed to load cookies from DB: %s", e)

    # 兜底：从磁盘文件读取
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
        """获取视频元数据。

        策略：先不带 cookies 尝试（android_vr 对公开视频无需认证）；
        若 YouTube 返回 Bot 检测错误，再带 cookies 重试一次。
        这样可以减少 cookies 的消耗，延长其有效期。
        """
        def _do_extract(with_cookies: bool) -> dict:
            cp = cookies_path if with_cookies else None
            opts = _base_opts(skip_download=True, cookies_path=cp)
            if with_cookies:
                # 带 cookies 时指定 player_client，android_vr 不支持 cookies 会被跳过
                opts["extractor_args"] = _YDL_PROXY_BLOCK
            # 不带 cookies 时不设置 extractor_args，让 yt-dlp 自动选择
            # （默认用 android_vr，无需认证，最稳定）
            logger.info(
                "ScraperService: extracting %s (cookies=%s)",
                url, "yes" if with_cookies else "no",
            )
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        # 第一次：不带 cookies
        info = None
        try:
            info = _do_extract(with_cookies=False)
        except Exception as e:
            err_str = str(e)
            # Bot 检测或需要登录 → 带 cookies 重试
            if ("Sign in" in err_str or "bot" in err_str.lower() or
                    "confirm" in err_str.lower()) and cookies_path:
                logger.warning(
                    "ScraperService: Bot detection without cookies, retrying with cookies (%s)",
                    url,
                )
                try:
                    info = _do_extract(with_cookies=True)
                except Exception as e2:
                    raise e2  # cookies 也失败，抛出最终错误
            else:
                raise  # 其他错误直接抛出

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

        # 排序：高分辨率 / 高码率在前
        video_options.sort(key=lambda f: f.get("height") or 0, reverse=True)
        audio_options.sort(key=lambda f: f.get("abr") or 0, reverse=True)

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
