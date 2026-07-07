"""下载相关 Pydantic Schemas

复刻自 docs/design/02-api-design.md §2.2.1
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Literal, Optional
from datetime import datetime


class DownloadCheckRequest(BaseModel):
    """POST /api/downloads/check 请求体"""
    url: HttpUrl


class ExistingVideoInfo(BaseModel):
    id: int
    title: str
    quality_label: Optional[str]
    file_size: int
    last_position: float


class DownloadCheckResponse(BaseModel):
    conflict: bool
    youtube_id: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[int] = None
    is_playlist: bool = False
    playlist_entries: Optional[list[dict]] = None
    existing_video: Optional[ExistingVideoInfo] = None


class DownloadCreateRequest(BaseModel):
    """POST /api/downloads 请求体"""
    url: HttpUrl
    format_type: Literal["video"] = "video"     # 已裁切仅音频
    quality: Literal["best", "1080p", "720p", "480p", "worst"]
    overwrite: bool = False
    download_subtitles: bool = False             # 字幕已确认不做，预留


class DownloadTaskRead(BaseModel):
    id: int
    url: str
    youtube_id: Optional[str]
    title: Optional[str]
    format_type: str
    quality: str
    status: str
    progress: float
    speed: Optional[str]
    eta: Optional[str]
    error_message: Optional[str]
    retry_count: int
    max_retries: int
    created_at: datetime
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True
