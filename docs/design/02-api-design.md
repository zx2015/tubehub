# 02. API 设计

> 后端 FastAPI 路由 + Pydantic Schema 设计。基于需求 02/03/05/06/07 已确认的接口集。

## 2.1 RESTful 路由总表

| 模块 | Method | Path | 用途 |
|------|--------|------|------|
| **下载** | POST | `/api/downloads/check` | 前置 check：检测 URL 是否已在库中 |
| | POST | `/api/downloads` | 创建下载任务（支持单视频/歌单批量） |
| | GET | `/api/downloads` | 列出任务（支持 status 过滤） |
| | GET | `/api/downloads/{id}` | 任务详情 |
| | DELETE | `/api/downloads/{id}` | 取消/删除任务 |
| | POST | `/api/downloads/{id}/retry` | 手动重试失败任务 |
| | GET | `/api/downloads/{id}/stream` | SSE 实时进度推送 |
| **视频** | GET | `/api/videos` | 视频库列表（搜索/排序/分页） |
| | GET | `/api/videos/{id}` | 视频详情 |
| | DELETE | `/api/videos/{id}` | 删除单个视频（含文件 + CASCADE 历史） |
| | POST | `/api/videos/batch-delete` | 批量删除 |
| | GET | `/api/videos/{id}/thumbnail` | 返回本地缩略图 |
| | GET | `/api/videos/{id}/stream` | 视频流式播放（Range Request） |
| | PATCH | `/api/videos/{id}/progress` | 更新播放进度 |
| **历史** | GET | `/api/history` | 列出历史 |
| | DELETE | `/api/history/{id}` | 删除单条历史 |
| | POST | `/api/history/clear` | 清空历史（可带 before_days 参数） |
| **设置** | GET | `/api/settings/cookies` | 获取 Cookie 状态 |
| | POST | `/api/settings/cookies` | 上传 Cookie |
| | DELETE | `/api/settings/cookies` | 清除 Cookie |
| | GET | `/api/settings/proxy` | 获取代理配置 |
| | PUT | `/api/settings/proxy` | 保存代理配置 |
| | POST | `/api/settings/proxy/test` | 测试代理连通性 |
| **运维** | GET | `/api/health` | 健康检查 |

## 2.2 Pydantic Schema 设计

> 文件位置：`backend/app/schemas/`

### 2.2.1 下载任务（`download.py`）

```python
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
```

### 2.2.2 视频（`video.py`）

```python
class VideoRead(BaseModel):
    id: int
    youtube_id: str
    title: str
    uploader: Optional[str]
    source_url: str
    upload_date: Optional[str]
    duration: Optional[int]
    thumbnail_path: Optional[str]
    file_size: Optional[int]
    width: Optional[int]
    height: Optional[int]
    quality_label: Optional[str]
    last_position: float = 0
    last_watched_at: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True


class VideoProgressUpdate(BaseModel):
    position: float = Field(ge=0)
    duration: float = Field(ge=0)


class BatchDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
```

### 2.2.3 设置（`settings.py`）

```python
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
```

## 2.3 路由签名（关键示例）

### 2.3.1 创建下载任务

```python
# backend/app/api/downloads.py
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.post("", response_model=list[DownloadTaskRead], status_code=201)
async def create_download(
    req: DownloadCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """创建下载任务，返回扁平化的任务列表（歌单也展开为多个 task）"""
    # 1. 调用 scraper.parse_url() 拿到 youtube_id 与 metadata
    # 2. 如果是歌单 → 循环写入多条 task，全部 status=queued
    # 3. 如果是单视频 → 写入一条 task
    # 4. 调度器会自动拾取
    ...


@router.post("/check", response_model=DownloadCheckResponse)
async def check_download(req: DownloadCheckRequest, db: AsyncSession = Depends(get_db)):
    """前置 check：仅解析元数据，不下载"""
    ...
```

### 2.3.2 SSE 进度推送

```python
@router.get("/{task_id}/stream")
async def stream_progress(task_id: int):
    """SSE 流：每 1 秒推送一次进度，直到状态变为 Ready/Failed/Cancelled"""
    async def event_generator():
        while True:
            task = await get_task(task_id)
            yield f"data: {task.model_dump_json()}\n\n"
            
            if task.status in ("ready", "failed", "cancelled"):
                break
            await asyncio.sleep(1)
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

## 2.4 错误码体系

| HTTP 状态码 | 含义 | 触发场景 |
|------------|------|----------|
| 200 | OK | 正常 GET |
| 201 | Created | 资源创建成功 |
| 204 | No Content | DELETE 成功 |
| 400 | Bad Request | URL 非法、参数错误 |
| 404 | Not Found | 资源不存在 |
| 409 | Conflict | 资源冲突（如并发删除） |
| 422 | Validation Error | Pydantic 校验失败 |
| 500 | Internal Error | 后端未捕获异常 |

错误响应统一格式：

```json
{
  "detail": "错误描述",
  "code": "TUBEHUB_XXX_YYY"
}
```

---

## Related

- [01-database-schema.md](01-database-schema.md) — 数据库 Schema
- [03-yt-dlp-integration.md](03-yt-dlp-integration.md) — yt-dlp 集成
- [06-error-handling.md](06-error-handling.md) — 错误处理