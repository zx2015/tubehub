# 02. API 设计

> 后端 FastAPI 路由 + Pydantic Schema 设计。基于需求 02/03/05/06/07 已确认的接口集。

## 2.1 RESTful 路由总表（按当前代码）

| 模块 | Method | Path | 用途 | 当前状态 |
|------|--------|------|------|------|
| **下载** | POST | `/api/downloads/check` | 获取信息，返回 `video_formats` / `audio_formats` | ✅ 已实现 |
| | POST | `/api/downloads` | 创建任务（单视频） | ✅ 已实现 |
| | GET | `/api/downloads` | 列出任务（支持 `status`） | ✅ 已实现 |
| | GET | `/api/downloads/{id}` | 任务详情 | ✅ 已实现 |
| | DELETE | `/api/downloads/{id}` | 进行中任务取消；终态任务删除 | ✅ 已实现 |
| | POST | `/api/downloads/{id}/retry` | 手动重试 failed/cancelled | ✅ 已实现 |
| | GET | `/api/downloads/{id}/stream` | SSE 进度流 | ✅ 已实现 |
| **视频** | GET | `/api/videos` | 视频库列表（`q` / `limit` / `offset`） | ✅ 已实现 |
| | GET | `/api/videos/{id}` | 视频详情 | ⚠️ 占位返回 |
| | DELETE | `/api/videos/{id}` | 删除视频记录 + 历史记录 | ✅ 已实现（未做物理文件删除） |
| | POST | `/api/videos/batch-delete` | 批量删除 | ⚠️ 占位返回 |
| | GET | `/api/videos/{id}/thumbnail` | 缩略图 | ⚠️ 占位返回 |
| | GET | `/api/videos/{id}/stream` | 视频流 | ⚠️ 占位返回 |
| | PATCH | `/api/videos/{id}/progress` | 播放进度上报 | ⚠️ 占位返回 |
| **历史** | GET | `/api/history` | 列出历史 | ✅ 已实现 |
| | DELETE | `/api/history/{id}` | 删除单条历史 | ⚠️ 占位返回 |
| | POST | `/api/history/clear` | 清空历史 | ⚠️ 占位返回 |
| **设置** | GET | `/api/settings/cookies` | 获取 Cookie 状态 | ✅ 已实现 |
| | POST | `/api/settings/cookies` | 上传 Cookie（`text/plain`） | ✅ 已实现 |
| | DELETE | `/api/settings/cookies` | 清除 Cookie | ✅ 已实现 |
| **运维** | GET | `/api/health` | 健康检查 | ✅ 已实现 |

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
    video_format_id: Optional[int]
    audio_format_id: Optional[int]
    file_size: int
    last_position: float


class VideoFormatOption(BaseModel):
    """前端下拉框中的一项格式。"""
    id: str
    label: str          # 人类可读："{height}p ({ext} · {vcodec} · {tbr:.0f}kbps)"
    ext: Optional[str] = None
    height: Optional[int] = None
    width: Optional[int] = None
    vcodec: Optional[str] = None
    abr: Optional[float] = None
    acodec: Optional[str] = None
    tbr: Optional[float] = None
    filesize: Optional[int] = None


class DownloadCheckResponse(BaseModel):
    conflict: bool
    youtube_id: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[int] = None
    is_playlist: bool = False
    playlist_entries: Optional[list[dict]] = None
    existing_video: Optional[ExistingVideoInfo] = None
    uploader: Optional[str] = None
    video_formats: list[VideoFormatOption] = []
    audio_formats: list[VideoFormatOption] = []


class DownloadCreateRequest(BaseModel):
    """双 format_id 创建任务。"""
    url: HttpUrl
    video_format_id: Optional[int] = None
    audio_format_id: Optional[int] = None
    playlist_entries: Optional[list[dict]] = None
    overwrite: bool = False


class DownloadTaskRead(BaseModel):
    id: int
    url: str
    youtube_id: Optional[str]
    title: Optional[str]
    # v3.0：使用双 format_id
    video_format_id: Optional[int]
    audio_format_id: Optional[int]
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
    video_format_id: Optional[int]
    audio_format_id: Optional[int]
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
    """SSE 流：每 1 秒推送一次进度，最多 1 小时"""
    async def event_generator():
        while True:
            task = await get_task(task_id)
            yield f"data: {task.model_dump_json()}\n\n"
            
            if task.status in ("ready", "failed", "cancelled"):
                break
            await asyncio.sleep(1)
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

## 2.4 错误响应

| HTTP 状态码 | 含义 | 触发场景 |
|------------|------|----------|
| 200/201/204 | 成功 | 正常请求 |
| 400 | 参数或业务校验失败 | 如格式 ID 不合法 |
| 404 | 资源不存在 | 如任务/视频不存在 |
| 409 | 资源冲突 | 重复下载且未开启 overwrite |
| 422 | 请求体验证失败 | Pydantic 校验失败 |
| 500 | 未捕获异常 | 全局异常处理中间件 |

全局异常与验证异常会返回带 `code` 的统一结构；路由里显式 `HTTPException` 常仅包含 `detail`。

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