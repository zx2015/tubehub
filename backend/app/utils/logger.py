"""loguru 日志配置

详见 docs/design/06-error-handling.md §6.2
"""
import os
import sys

from loguru import logger

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# 移除默认 handler
logger.remove()

# 控制台输出（人类可读，INFO 级别）
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
           "<level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
           "<level>{message}</level>",
)

# 文件输出（DEBUG 级别 + 滚动）
logger.add(
    f"{LOG_DIR}/tubehub.log",
    level="DEBUG",
    rotation="20 MB",
    retention="14 days",
    compression="zip",
    encoding="utf-8",
)

# yt-dlp 独立日志（避免污染业务日志）
logger.add(
    f"{LOG_DIR}/ytdlp.log",
    level="INFO",
    filter=lambda record: record["name"].startswith("yt_dlp"),
    rotation="50 MB",
)

# FFmpeg 独立日志
logger.add(
    f"{LOG_DIR}/ffmpeg.log",
    level="INFO",
    filter=lambda record: "ffmpeg" in record["message"].lower(),
    rotation="50 MB",
)
