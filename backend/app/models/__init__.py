from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, Date, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Video(Base):
    """视频主表：视频入库后存放在此，download_tasks 仅作流水记录"""
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    youtube_id = Column(String(16), nullable=False, unique=True, index=True)
    title = Column(String(512), nullable=False)
    uploader = Column(String(256))
    uploader_id = Column(String(64))
    source_url = Column(Text, nullable=False, default="")
    upload_date = Column(Date)
    duration = Column(Integer)  # 秒

    description = Column(Text)
    thumbnail_path = Column(String(512))

    file_path = Column(Text, nullable=False)
    file_size = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)
    fps = Column(Float)
    vcodec = Column(String(32))
    acodec = Column(String(32))
    container = Column(String(16))
    format_type = Column(String(16), default="video")
    quality_label = Column(String(32))

    last_position = Column(Float, default=0)
    last_watched_at = Column(DateTime)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    play_history = relationship(
        "PlayHistory", back_populates="video",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_videos_uploader", "uploader"),
        Index("idx_videos_created_at_desc", "created_at"),
    )


class DownloadTask(Base):
    """下载任务流水表（生命周期 3 ~ 30 天，详见需求 02 §2.9）"""
    __tablename__ = "download_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(Text, nullable=False)
    youtube_id = Column(String(16), index=True)
    title = Column(String(512))
    format_type = Column(String(16), nullable=False)
    quality = Column(String(16), nullable=False)

    status = Column(String(16), nullable=False, default="pending", index=True)
    progress = Column(Float, default=0)
    speed = Column(String(32))
    eta = Column(String(16))
    downloaded_bytes = Column(Integer, default=0)
    total_bytes = Column(Integer, default=0)

    error_message = Column(Text)
    save_path = Column(Text)

    # 02 §2.8 自动重试字段
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    last_attempt_at = Column(DateTime)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False,
                        default=datetime.utcnow, onupdate=datetime.utcnow)
    finished_at = Column(DateTime)

    __table_args__ = (
        Index("idx_downloads_created_at_desc", "created_at"),
    )


class PlayHistory(Base):
    """播放历史：30 天后由 APScheduler 自动清理（需求 05 §5.6）"""
    __tablename__ = "play_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"),
                      nullable=False, unique=True)
    position = Column(Float, default=0)
    duration = Column(Float, default=0)
    progress_percent = Column(Float, default=0)
    completed = Column(Boolean, default=False)
    first_watched_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_watched_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    watch_count = Column(Integer, default=1)

    video = relationship("Video", back_populates="play_history")

    __table_args__ = (
        Index("idx_history_last_watched_desc", "last_watched_at"),
    )


class SystemSetting(Base):
    """通用 KV 存储：cookies、proxy 等运行时可配置项"""
    __tablename__ = "system_settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False,
                        default=datetime.utcnow, onupdate=datetime.utcnow)