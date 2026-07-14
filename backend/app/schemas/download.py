"""下载相关 Pydantic Schemas (v3.0 双 select 严格 list-formats)

复刻自 docs/design/02-api-design.md §2.2.1
"""
from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Optional, Any
from datetime import datetime


# ----------------------------------------------------------------------
# 视频格式选项 (单条)
# ----------------------------------------------------------------------
class VideoFormatOption(BaseModel):
    id: str                          # yt-dlp format_id（字符串，例如 "137"）
    label: str                       # 人类可读，例如 "1080p avc · 250MB · mp4 [137]"
    ext: Optional[str] = None
    height: Optional[int] = None
    width: Optional[int] = None
    vcodec: Optional[str] = None
    abr: Optional[float] = None
    acodec: Optional[str] = None
    tbr: Optional[float] = None
    filesize: Optional[int] = None


# ----------------------------------------------------------------------
# /api/downloads/check — 🔍 检测冲突 (v3.0：返回真实 list-formats)
# ----------------------------------------------------------------------
class DownloadCheckRequest(BaseModel):
    url: HttpUrl


class ExistingVideoInfo(BaseModel):
    id: int
    title: str
    video_format_id: Optional[str] = None
    audio_format_id: Optional[str] = None
    file_size: int
    last_position: float

    @field_validator("video_format_id", "audio_format_id", mode="before")
    @classmethod
    def coerce_format_id_to_str(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        return str(v)


class DownloadCheckResponse(BaseModel):
    conflict: bool
    youtube_id: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[int] = None
    uploader: Optional[str] = None
    is_playlist: bool = False
    playlist_entries: Optional[list[dict]] = None
    existing_video: Optional[ExistingVideoInfo] = None
    # v3.0 双 select 下拉项
    video_formats: list[VideoFormatOption] = []
    audio_formats: list[VideoFormatOption] = []


# ----------------------------------------------------------------------
# /api/downloads — 创建任务（提交双 format_id）
# ----------------------------------------------------------------------
class PlaylistEntryCreate(BaseModel):
    """歌单模式下，单条子视频的格式选择。"""
    youtube_id: str
    title: Optional[str] = None
    video_format_id: int
    audio_format_id: int


class DownloadCreateRequest(BaseModel):
    url: HttpUrl
    # v3.0 双 select 严格模式：format_id 为字符串（yt-dlp 可返回非纯数字 ID 如 "140-drc"）
    # 同时接受前端传来的 int（如 137），自动转为 str
    video_format_id: Optional[str] = None
    audio_format_id: Optional[str] = None
    playlist_entries: Optional[list[PlaylistEntryCreate]] = None
    overwrite: bool = False

    @field_validator("video_format_id", "audio_format_id", mode="before")
    @classmethod
    def coerce_format_id_to_str(cls, v: Any) -> Optional[str]:
        """兼容前端传 int（137）或 str（"140-drc"），统一转为字符串。"""
        if v is None:
            return None
        return str(v)


# ----------------------------------------------------------------------
# /api/downloads/{id} — 读取任务
# ----------------------------------------------------------------------
class DownloadTaskRead(BaseModel):
    id: int
    url: str
    youtube_id: Optional[str] = None
    title: Optional[str] = None
    video_format_id: Optional[str] = None
    audio_format_id: Optional[str] = None
    status: str
    progress: float
    speed: Optional[str] = None
    eta: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int
    max_retries: int
    created_at: datetime
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True
