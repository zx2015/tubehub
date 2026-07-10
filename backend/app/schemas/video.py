"""视频相关 Pydantic Schemas

复刻自 docs/design/02-api-design.md §2.2.2
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class VideoRead(BaseModel):
    id: int
    youtube_id: str
    title: str
    uploader: Optional[str] = None
    source_url: str = ""
    upload_date: Optional[str] = None
    duration: Optional[int] = None
    thumbnail_path: Optional[str] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    quality_label: Optional[str] = None   # Video 模型无此列，兼容旧客户端保留
    last_position: float = 0
    last_watched_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class VideoProgressUpdate(BaseModel):
    position: float = Field(ge=0)
    duration: float = Field(ge=0)


class BatchDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
