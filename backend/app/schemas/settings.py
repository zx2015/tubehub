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


class McpConfig(BaseModel):
    """MCP Browser 连接配置"""
    url: str = ""                    # e.g. http://192.168.110.123:9000
    token: str = ""                  # Bearer token（返回时 mask）
    enabled: bool = False            # 是否已配置且可用


class McpSyncResult(BaseModel):
    """MCP cookies 同步结果"""
    success: bool
    message: str
    cookie_count: Optional[int] = None   # 同步到的 cookie 数量
    file_size: Optional[int] = None      # 写入后的文件大小（字节）
