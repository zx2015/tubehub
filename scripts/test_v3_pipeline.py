"""scripts/test_v3_pipeline.py
v3.0 严格双 select 端到端测试。
"""
import asyncio
import os
import sys

# 启用代理（本地 venv 无 yt-dlp cookies，但走代理可拿到完整 formats）
os.environ["HTTP_PROXY"] = "http://10.182.67.191:8080"
os.environ["HTTPS_PROXY"] = "http://10.182.67.191:8080"

from yt_dlp import YoutubeDL

URL = "https://www.youtube.com/watch?v=nwMKuChwpMo"
OUT_DIR = "/tmp/tubehub_v3_test"

YDL_OPTS_BASE = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": False,
    "noplaylist": True,
    "extractor_args": {"youtube": {"player_client": ["default", "ios", "android", "web_safari", "tv", "web"]}},
}


def classify_formats(info):
    """严格分类: vcodec != none AND acodec == none -> 视频; acodec != none AND vcodec == none -> 音频; 其余排除"""
    video_only, audio_only = [], []
    for f in info.get("formats", []):
        if not f.get("url") and not f.get("manifest_url"):
            continue
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        # 排除缩略图 (vcodec == images)
        if vcodec == "images" or acodec == "images":
            continue
        # 排除 progressive (双轨) - 既然我们走 f"{vid}+{aid}，progressive 会引起冲突
        if vcodec != "none" and acodec != "none":
            continue
        if vcodec != "none" and acodec == "none":
            video_only.append(f)
        elif acodec != "none" and vcodec == "none":
            audio_only.append(f)
    return video_only, audio_only


def fmt_video_label(f):
    h = f.get("height")
    fps = f.get("fps") or ""
    vcodec = f.get("vcodec", "?")
    size = f.get("filesize") or f.get("filesize_approx")
    ext = f.get("ext", "?")
    fid = f.get("format_id", "?")
    parts = []
    if h: parts.append(f"{h}p{fps}")
    if vcodec != "none": parts.append(vcodec)
    if size: parts.append(f"{size/1024/1024:.1f}MB")
    parts.append(ext)
    return f"{' · '.join(parts)} [{fid}]"


def fmt_audio_label(f):
    abr = f.get("abr") or f.get("tbr")
    acodec = f.get("acodec", "?")
    size = f.get("filesize") or f.get("filesize_approx")
    ext = f.get("ext", "?")
    fid = f.get("format_id", "?")
    parts = []
    if abr: parts.append(f"{int(abr)}kbps")
    if acodec != "none": parts.append(acodec)
    if size: parts.append(f"{size/1024/1024:.1f}MB")
    parts.append(ext)
    return f"{' · '.join(parts)} [{fid}]"


def main():
    print("=" * 70)
    print("PHASE 1: extract_info 探测完整 formats")
    print("=" * 70)
    with YoutubeDL(YDL_OPTS_BASE) as ydl:
        info = ydl.extract_info(URL, download=False)
    print(f"标题:   {info.get('title', '?')}")
    print(f"ID:     {info.get('id', '?')}")
    print(f"时长:   {info.get('duration', 0)} 秒")
    print(f"原始 formats 总数: {len(info.get('formats', []))}")

    print()
    print("=" * 70)
    print("PHASE 2: 严格分类")
    print("=" * 70)
    videos, audios = classify_formats(info)
    print(f"视频轨 (video only): {len(videos)} 条")
    for f in videos:
        print(f"  {fmt_video_label(f)}")
    print(f"\n音频轨 (audio only): {len(audios)} 条")
    for f in audios:
        print(f"  {fmt_audio_label(f)}")

    if not videos or not audios:
        print("FAIL: 视频或音频列表为空")
        return

    # 选择 1080p 视频 + 129k m4a 音频（与您给的命令行一致）
    video_id = "137"
    audio_id = "140"
    if not any(f.get("format_id") == video_id for f in videos):
        video_id = videos[0]["format_id"]
    if not any(f.get("format_id") == audio_id for f in audios):
        audio_id = audios[0]["format_id"]
    print()
    print("=" * 70)
    print(f"PHASE 3: 选择 video={video_id} + audio={audio_id}")
    print("=" * 70)

    print()
    print("=" * 70)
    print(f"PHASE 4: 下载 {video_id}+{audio_id} 拼接流")
    print("=" * 70)
    os.makedirs(OUT_DIR, exist_ok=True)
    opts = dict(YDL_OPTS_BASE)
    opts.update({
        "format": f"{video_id}+{audio_id}",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(OUT_DIR, "%(title)s [%(id)s].%(ext)s"),
        "quiet": False,
    })
    with YoutubeDL(opts) as ydl:
        info2 = ydl.extract_info(URL, download=True)
        path = ydl.prepare_filename(info2)
    print()
    print("=" * 70)
    if os.path.exists(path):
        size_mb = os.path.getsize(path) / 1024 / 1024
        print(f"SUCCESS: {path} ({size_mb:.1f}MB)")
    else:
        # 查 OUT_DIR 找实际输出
        files = os.listdir(OUT_DIR)
        if files:
            for f in files:
                fp = os.path.join(OUT_DIR, f)
                if os.path.isfile(fp):
                    size_mb = os.path.getsize(fp) / 1024 / 1024
                    print(f"OUTPUT: {fp} ({size_mb:.1f}MB)")


if __name__ == "__main__":
    main()
