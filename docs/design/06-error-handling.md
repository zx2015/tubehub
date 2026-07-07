# 06. 错误处理与日志设计

## 6.1 全局错误中间件

> 文件位置：`backend/app/middleware.py`

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger


async def global_exception_handler(request: Request, exc: Exception):
    """捕获所有未处理异常，避免栈跟踪泄露"""
    logger.exception(f"Unhandled error: {request.method} {request.url.path} - {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal Server Error",
            "code": "TUBEHUB_INTERNAL_ERROR"
        }
    )


async def validation_exception_handler(request: Request, exc):
    """Pydantic 校验失败统一格式"""
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "code": "TUBEHUB_VALIDATION_ERROR"
        }
    )
```

## 6.2 日志规范（loguru）

```python
# backend/app/utils/logger.py
from loguru import logger
import sys
import os

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# 移除默认 handler
logger.remove()

# 控制台输出（人类可读，INFO 级别）
logger.add(sys.stdout, level="INFO",
           format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                  "<level>{level: <8}</level> | "
                  "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
                  "<level>{message}</level>")

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
```

## 6.3 错误码体系（已锁定）

| 错误码 | HTTP | 含义 |
|--------|------|------|
| `TUBEHUB_VALIDATION_ERROR` | 422 | 请求参数校验失败 |
| `TUBEHUB_URL_INVALID` | 400 | YouTube URL 非法 |
| `TUBEHUB_VIDEO_PRIVATE` | 404 | 视频私密或已删除 |
| `TUBEHUB_PROXY_FAIL` | 502 | 代理连接失败 |
| `TUBEHUB_DISK_FULL` | 507 | 磁盘空间不足 |
| `TUBEHUB_FCONFLICT_DELETE` | 409 | 视频正在被下载，无法删除 |
| `TUBEHUB_INTERNAL_ERROR` | 500 | 兜底异常 |
| `TUBEHUB_FFMPEG_MISSING` | 500 | 系统未检测到 FFmpeg |

## 6.4 SSE 推送协议设计

### 6.4.1 数据格式

```text
event: progress
data: {"id":1,"status":"downloading","progress":45.2,"speed":"1.2MiB/s","eta":"00:30"}

event: progress
data: {"id":1,"status":"merging","progress":99.0}

event: progress
data: {"id":1,"status":"ready","progress":100,"title":"xxx"}

event: error
data: {"code":"TUBEHUB_VIDEO_PRIVATE","detail":"视频不可访问"}
```

### 6.4.2 重连策略

- 前端 `EventSource` 断线后**自动重连**
- 后端通过查询参数 `last_event_id` 支持断点续传（可选实现，MVP 简化）

## 6.5 前端错误处理

```typescript
// utils/api.ts
async function apiCall<T>(url: string, options?: RequestInit): Promise<T> {
  const r = await fetch(url, options);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    // 抛出业务错误供 UI Toast 显示
    throw new ApiError(err.detail || r.statusText, err.code);
  }
  return r.json();
}

class ApiError extends Error {
  constructor(public detail: string, public code: string) {
    super(detail);
  }
}
```

---

## Related

- [00-architecture.md](00-architecture.md) — 整体架构
- [07-operations.md](07-operations.md) — 部署与运维