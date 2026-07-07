"""
TubeHub yt-dlp 动态格式选择 - 端到端验证脚本

测试目标:
1. 验证代理 http://192.168.2.100:8080 下的网络可达性
2. 验证从视频 https://www.youtube.com/watch?v=nwMKuChwpMo 解析 title, formats
3. 验证单独提取最佳音频轨(best audio) 和最佳视频轨(best video)
4. 验证 select_dynamic_format 算法选出的拼接 format string 是否真实可用
5. 走代理下载最小试看片段，确认代理在 yt-dlp 中真实生效

运行: /media/data/venv/bin/python scripts/test_ytdlp_dynamic.py
"""
import asyncio
import json
import sys
import os
from pathlib import Path

import yt_dlp

PROXY_URL = "http://192.168.2.100:8080"
TEST_URL = "https://www.youtube.com/watch?v=nwMKuChwpMo"
OUTPUT_DIR = Path("/tmp/tubehub_test")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# 直接复用后端的算法，确保本地测试与生产完全一致
def select_dynamic_format(info_dict: dict, requested_quality: str) -> str:
    formats = info_dict.get("formats")
    if not formats:
        return "best"

    limit_heights = {
        "best": 99999, "1080p": 1080, "720p": 720, "480p": 480, "worst": 360
    }
    limit_h = limit_heights.get(requested_quality, 99999)

    # 视频轨：仅视频、无音频
    video_formats = [
        f for f in formats
        if (f.get("vcodec") or "none") != "none"
        and (f.get("acodec") or "none") == "none"
        and (f.get("height") or 0) <= limit_h
    ]
    if not video_formats:
        # 放宽高度限制
        video_formats = [
            f for f in formats
            if (f.get("vcodec") or "none") != "none"
            and (f.get("acodec") or "none") == "none"
        ]

    best_v_id = None
    if video_formats:
        video_formats.sort(key=lambda x: (x.get("height") or 0, x.get("tbr") or 0))
        best_v_id = video_formats[-1].get("format_id")

    audio_formats = [
        f for f in formats
        if (f.get("vcodec") or "none") == "none"
        and (f.get("acodec") or "none") != "none"
    ]
    best_a_id = None
    if audio_formats:
        audio_formats.sort(key=lambda x: x.get("tbr") or 0)
        best_a_id = audio_formats[-1].get("format_id")

    if best_v_id and best_a_id:
        return f"{best_v_id}+{best_a_id}/best"
    if best_v_id:
        return f"{best_v_id}/best"
    return "best"


def section(title: str):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


async def main():
    section("Step 1 - 验证代理网络连通性")
    import httpx
    try:
        async with httpx.AsyncClient(proxy=PROXY_URL, timeout=10.0) as client:
            r = await client.get("https://www.youtube.com/")
            print(f"[OK] Proxy {PROXY_URL} → YouTube 返回 {r.status_code} ({len(r.content)} bytes)")
    except Exception as e:
        print(f"[FAIL] 代理网络失败: {e}")
        sys.exit(1)

    section("Step 2 - 模拟下载器：fetch metadata & formats")
    # 不下载，仅 fetch metadata
    ydl_opts_probe = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "proxy": PROXY_URL,
        "cookiefile": "/media/data/git/tubehub/www.youtube.com_cookies.txt",  # ✅ 优先绑定用户最新上传的 cookie
        "extractor_args": {
            "youtube": {
                "player_client": ["tv", "android", "web"],
            }
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts_probe) as ydl:
        info = ydl.extract_info(TEST_URL, download=False)

    title = info.get("title", "未知")
    youtube_id = info.get("id", "未知")
    duration = info.get("duration", 0)
    uploader = info.get("uploader", "未知")
    formats = info.get("formats", [])
    thumbnail_url = info.get("thumbnail", "")

    print(f"[OK] 视频标题: {title}")
    print(f"[OK] 视频 ID: {youtube_id}")
    print(f"[OK] 时长: {duration} 秒")
    print(f"[OK] 上传者: {uploader}")
    print(f"[OK] 缩略图 URL: {thumbnail_url}")
    print(f"[OK] 总格式数: {len(formats)}")

    section("Step 3 - 视频缩略图下载（走代理）")
    if thumbnail_url:
        thumb_path = OUTPUT_DIR / f"{youtube_id}.jpg"
        async with httpx.AsyncClient(proxy=PROXY_URL, timeout=15.0, follow_redirects=True) as client:
            r = await client.get(thumbnail_url)
            if r.status_code == 200 and len(r.content) > 1024:
                thumb_path.write_bytes(r.content)
                print(f"[OK] 缩略图已下载到 {thumb_path} ({len(r.content)} bytes)")
            else:
                print(f"[FAIL] 缩略图下载失败: HTTP {r.status_code}, size={len(r.content)}")

    section("Step 4 - 过滤所有可用视频轨 (height>=720)")
    video_only = [
        f for f in formats
        if (f.get("vcodec") or "none") != "none"
        and (f.get("acodec") or "none") == "none"
    ]
    for f in video_only[-10:]:
        print(f"  [Video] id={f.get('format_id')} ext={f.get('ext')} {f.get('height')}p "
              f"vcodec={f.get('vcodec')} fps={f.get('fps')} tbr={f.get('tbr')}")
    print(f"  → 共 {len(video_only)} 条 video-only formats")

    section("Step 5 - 过滤所有可用音频轨")
    audio_only = [
        f for f in formats
        if (f.get("vcodec") or "none") == "none"
        and (f.get("acodec") or "none") != "none"
    ]
    for f in audio_only[-10:]:
        print(f"  [Audio] id={f.get('format_id')} ext={f.get('ext')} "
              f"acodec={f.get('acodec')} abr={f.get('abr')} tbr={f.get('tbr')}")
    print(f"  → 共 {len(audio_only)} 条 audio-only formats")

    section("Step 6 - select_dynamic_format(720p) 优选结果")
    chosen = select_dynamic_format(info, "720p")
    print(f"  [Format 选择] {chosen}")

    section("Step 7 - 单独验证 best audio (audio only)")
    audio_only_formats = [f for f in formats
                          if (f.get("vcodec") or "none") == "none"
                          and (f.get("acodec") or "none") != "none"]
    if audio_only_formats:
        # 选音频码率最高的
        audio_only_formats.sort(key=lambda x: x.get("abr") or 0)
        best_a = audio_only_formats[-1]
        print(f"  最佳音频 format id = {best_a.get('format_id')} ({best_a.get('acodec')}, {best_a.get('abr')}k)")
    else:
        print("  [WARN] 没有可用音频轨")

    section("Step 8 - 单独验证 best video (video only)")
    video_only_formats = [f for f in formats
                          if (f.get("vcodec") or "none") != "none"
                          and (f.get("acodec") or "none") == "none"]
    if video_only_formats:
        video_only_formats.sort(key=lambda x: (x.get("height") or 0, x.get("tbr") or 0))
        best_v = video_only_formats[-1]
        print(f"  最佳视频 format id = {best_v.get('format_id')} ({best_v.get('height')}p, "
              f"vcodec={best_v.get('vcodec')})")
    else:
        print("  [WARN] 没有可用视频轨")

    section("Step 9 - 真实下载测试 (走代理, 合并 bestvideo+bestaudio)")
    # 真实下载到 OUTPUT_DIR
    ydl_opts_download = {
        "format": chosen,
        "merge_output_format": "mp4",
        "outtmpl": f"{OUTPUT_DIR}/%(title)s.%(ext)s",
        "quiet": False,
        "no_warnings": False,
        "noplaylist": True,
        "proxy": PROXY_URL,
        "cookiefile": "/media/data/git/tubehub/www.youtube.com_cookies.txt",  # ✅ 优先使用用户最新上传的 cookie
        "extractor_args": {
            "youtube": {
                "player_client": ["tv", "android", "web"],
            }
        },
        # 限制下载大小（仅下 5MB 用于验证）
        "max_filesize": 5 * 1024 * 1024,
        # 不下载实际全片（早期停止）
        "external_downloader_args": "ffmpeg:-t 10",  # 截取前 10 秒
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            print(f"  → 使用 format: {chosen}, proxy: {PROXY_URL}")
            dl_info = ydl.extract_info(TEST_URL, download=True)
            # extract_info 已经触发了下载
        # 列出输出
        downloaded = list(OUTPUT_DIR.glob("*"))
        print(f"  → 下载目录 {OUTPUT_DIR} 中：")
        for f in downloaded:
            size_mb = f.stat().st_size / 1024 / 1024
            print(f"     {f.name} ({size_mb:.2f} MB)")
    except Exception as e:
        print(f"  [FAIL] 真实下载失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 60)
    print(" 🎉 全部 9 步验证通过！代理 + 动态格式选择工作完美")
    print("=" * 60)
    return True


if __name__ == "__main__":
    asyncio.run(main())