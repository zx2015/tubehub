"""设置相关 Pydantic Schemas

复刻自 docs/design/02-api-design.md §2.2.3
"""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


class CookieStatus(BaseModel):
    has_cookie: bool
    updated_at: Optional[datetime] = None
    file_size: Optional[int] = None   # 字节
    note: str = "Cookie 内容不返回，仅返回元信息"


class ProxyConfig(BaseModel):
    enabled: bool
    scheme: Literal["http", "https", "socks5"]
    host: str
    port: int = Field(ge=1, le=65535)
    username: str = ""
    password: str = ""


class ProxyConfigPublic(BaseModel):
    """对外返回时屏蔽 password 字段"""
    enabled: bool
    scheme: Literal["http", "https", "socks5"]
    host: str
    port: int
    username: str = ""


class ProxyTestResponse(BaseModel):
    ok: bool
    latency_ms: Optional[int] = None
    status_code: Optional[int] = None
    error: Optional[str] = None
