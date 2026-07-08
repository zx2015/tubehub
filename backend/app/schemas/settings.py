"""设置相关 Pydantic Schemas (极简自愈版)

仅保留 CookieStatus 结构，其余由系统环境变量接管。
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class CookieStatus(BaseModel):
    has_cookie: bool
    updated_at: Optional[datetime] = None
    file_size: Optional[int] = None   # 字节
    note: str = "Cookie 内容不返回，仅返回元信息"
