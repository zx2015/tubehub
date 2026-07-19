"""视频相关 Pydantic Schemas

复刻自 docs/design/02-api-design.md §2.2.2
"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date
from typing import Optional, Any


class VideoRead(BaseModel):
    id: int
    youtube_id: str
    title: str
    uploader: Optional[str] = None
    source_url: str = ""
    upload_date: Optional[str] = None   # 前端展示用字符串，如 "2023-10-15"
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

    @field_validator("upload_date", mode="before")
    @classmethod
    def coerce_upload_date(cls, v: Any) -> Optional[str]:
        """兼容 datetime.date 对象和字符串，统一转为 ISO 格式字符串。"""
        if v is None:
            return None
        if isinstance(v, date):
            return v.isoformat()   # "2023-10-15"
        return str(v)


class VideoProgressUpdate(BaseModel):
    position: float = Field(ge=0)
    duration: float = Field(ge=0)


class BatchDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
