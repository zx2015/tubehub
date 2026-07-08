# 03. 视频库与缩略图需求

> 来源：用户需求 §3

## 3.1 缩略图来源分析（重要 ⚠️）

### 3.1.1 YouTube 缩略图 URL 规律

YouTube 为每个视频预生成多个固定尺寸的缩略图，**无需调用 API 即可获取**：

| 尺寸 | URL 模式 | 用途 |
|------|----------|------|
| `default` | `https://img.youtube.com/vi/{video_id}/default.jpg` | 120×90，最小 |
| `mqdefault` | `https://img.youtube.com/vi/{video_id}/mqdefault.jpg` | 320×180，中等 |
| `hqdefault` | `https://img.youtube.com/vi/{video_id}/hqdefault.jpg` | 480×360，高质量（默认） |
| `sddefault` | `https://img.youtube.com/vi/{video_id}/sddefault.jpg` | 640×480，标清 |
| `maxresdefault` | `https://img.youtube.com/vi/{video_id}/maxresdefault.jpg` | 1280×720，最高画质 |

### 3.1.2 缩略图下载与缓存（已确认 ✅ 必须走代理）

> 决策（2026-07-07）：**缩略图必须下载到本地，且下载时必须走代理**（与 yt-dlp 代理保持一致）。

- **路径**：`data/thumbnails/{video_id}.jpg`
- **命名**：使用 YouTube `video_id` 作为文件名（避免标题含特殊字符）
- **首选尺寸**：`hqdefault`（兼容性最好，几乎所有视频都有）
- **降级链**：`hqdefault` (404) → `mqdefault` → `default` → 返回默认占位图
- **下载方式**：FastAPI 后端通过 `httpx` 异步下载，**必须使用与 yt-dlp 相同的代理配置**
- **触发时机**：
  - 视频入库时（`download_task` Ready → `videos` INSERT）
  - 用户首次访问视频库缩略图时（懒加载兜底）
- **缓存策略**：下载一次后保存到本地，永久缓存（除非视频被删除）

### 3.1.3 缩略图下载服务实现

```python
# services/thumbnail.py
import httpx
import os

THUMBNAIL_DIR = "data/thumbnails"
SIZES_TRY_ORDER = ["hqdefault", "mqdefault", "default"]

async def download_thumbnail(video_id: str, proxy_url: str | None = None) -> str | None:
    """下载 YouTube 缩略图到本地，优先尝试高画质"""
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    save_path = os.path.join(THUMBNAIL_DIR, f"{video_id}.jpg")

    # 已缓存直接返回
    if os.path.exists(save_path):
        return save_path

    # 降级链下载
    for size in SIZES_TRY_ORDER:
        url = f"https://img.youtube.com/vi/{video_id}/{size}.jpg"
        try:
            async with httpx.AsyncClient(
                proxy=proxy_url,    # ✅ 必须走代理
                timeout=10.0,
                follow_redirects=True,
            ) as client:
                r = await client.get(url)
                if r.status_code == 200 and len(r.content) > 1000:
                    with open(save_path, "wb") as f:
                        f.write(r.content)
                    logger.info(f"Thumbnail saved: {video_id} ({size}, {len(r.content)} bytes)")
                    return save_path
        except Exception as e:
            logger.warning(f"Thumbnail {size} fetch failed for {video_id}: {e}")
            continue

    # 全部失败：返回默认占位图
    logger.error(f"All thumbnail sizes failed for {video_id}")
    return "static/placeholder-thumbnail.jpg"
```

### 3.1.4 注意事项

- **代理自动捕获**（v2.0.0）：缩略图下载通过 `httpx.AsyncClient()` **隐式**读取系统环境变量 `HTTP_PROXY`，无需任何手动配置，与 yt-dlp 行为一致
- **文件大小校验**：YouTube 返回的占位 `default.jpg` 通常 < 1KB，需过滤避免保存无效图
- **并发控制**：批量入库时（如歌单），缩略图下载应有信号量限流，避免对 YouTube 造成压力
- **缩略图不再依赖 yt-dlp**：关闭 `writethumbnail` 选项（节省带宽，统一从后端下载）

## 3.2 视频元数据

> 来源：yt-dlp `info_dict` + 必要时前端补全

```python
class Video:
    id: int                     # TubeHub 主键
    youtube_id: str             # YouTube video_id（11 位，唯一）
    title: str                  # 视频标题
    uploader: str               # 频道名
    uploader_id: str            # 频道 ID
    source_url: str             # 原始 YouTube 链接 ✅ 新增
    upload_date: date           # YouTube 上传日期
    duration: int               # 秒数
    description: str            # 视频简介（可能很长）
    thumbnail_path: str         # 本地缩略图路径
    file_path: str              # 视频文件本地路径
    file_size: int              # 字节
    width: int                  # 分辨率宽
    height: int                 # 分辨率高
    fps: float                  # 帧率
    vcodec: str                 # 视频编码（avc1, vp9, av01）
    acodec: str                 # 音频编码（mp4a, opus）
    container: str              # 容器（mp4, mkv, webm）
    format_type: str            # video | audio（继承自下载任务）
    quality_label: str          # "1080p", "720p" 等

    # 播放进度
    last_position: float        # 上次播放位置（秒）
    last_watched_at: datetime

    created_at: datetime        # 入库时间
```

## 3.3 文件命名（已确认 ✅）

> 用户决策：**使用视频标题**作为文件名（人类可读）

### 3.3.1 命名规则

- **模板**：`{sanitize(title)}[{youtube_id}].{ext}`
  - 示例：`Python 教程 [dQw4w9WgXcQ].mp4`
  - `[youtube_id]` 后缀保证唯一性，避免标题重名冲突
- **扩展名**：与下载容器一致（`.mp4` / `.mkv` / `.webm` / `.m4a`）
- **路径**：`data/videos/{uploader}/{sanitize(title)}[{youtube_id}].{ext}`
  - 按上传者分目录，便于管理
  - 上传者名同样做 sanitization

### 3.3.2 标题 sanitization 规则

```python
import re
from pathlib import Path

def sanitize_filename(name: str, max_length: int = 200) -> str:
    """将标题转为合法文件名"""
    # 1. 移除 Windows 非法字符 <>:"/\|?*
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # 2. 移除控制字符
    name = re.sub(r'[\x00-\x1f\x7f]', '', name)
    # 3. 替换空白为下划线
    name = re.sub(r'\s+', '_', name.strip())
    # 4. 截断到 max_length（预留后缀空间）
    if len(name) > max_length:
        name = name[:max_length].rstrip('_')
    # 5. 避免以 . 结尾（Windows 兼容）
    name = name.rstrip('.')
    # 6. 兜底
    return name or "untitled"
```

### 3.3.3 文件路径存储

- DB 中 `videos.file_path` 存储**绝对路径**（避免相对路径在不同工作目录下解析失败）
- 删除视频时，根据 `file_path` 删除文件 + 数据库记录

## 3.4 重复检测与重下策略（已确认 ✅）

> 用户决策：**默认覆盖已下载文件**，但发现重复时必须**提示用户**确认。

### 3.4.1 检测时机

**前置检测**（推荐）：在用户提交下载表单、调用 `POST /api/downloads` 之前，前端先调用 `POST /api/downloads/check`：

```
前端: 用户点 "开始下载"
   │
   ▼
POST /api/downloads/check { url, format_type, quality }
   │
   ▼
后端用 yt-dlp 解析 URL（不下载），返回 youtube_id + 标题 + 现有记录
   │
   ├─ 库中无此 youtube_id → 直接 POST /api/downloads 入队
   └─ 库中已存在 → 返回 existing_video 详情 + conflict=true
        │
        ▼
   前端弹出确认对话框：
   ┌─────────────────────────────────────────────┐
   │ ⚠️ 检测到该视频已在媒体库中                  │
   │                                              │
   │  标题：Python 教程                            │
   │  已下载于：2026-06-15                         │
   │  当前画质：1080p                              │
   │  文件大小：256 MB                             │
   │  播放进度：45%                                │
   │                                              │
   │  新下载参数：                                 │
   │  格式：视频  画质：4K                         │
   │                                              │
   │  确认操作：                                   │
   │  ◉ 覆盖原文件（删除旧文件后下载新版本）        │
   │  ○ 保留旧文件，取消本次下载                   │
   │                                              │
   │            [取消]  [确认下载]                  │
   └─────────────────────────────────────────────┘
        │
        ├─ [取消] → 不发起 POST /api/downloads
        └─ [确认下载] → POST /api/downloads { overwrite: true }
```

### 3.4.2 覆盖行为（已确认）

- `overwrite: true` 时：
  - 下载完成后，**先删除**旧文件（`data/videos/...`）再写入新文件
  - **保留** DB 中的旧记录 ID，`UPDATE` 元数据（标题、上传者、画质、文件路径、大小）
  - **重置** `last_position = 0`（新视频进度从 0 开始）
  - **保留** `play_history` 历史记录（外键不删除），便于用户回顾观看历史
  - 缩略图沿用本地缓存，不重复下载

### 3.4.3 取消下载的清理

- 用户取消进行中的下载：
  - 删除 yt-dlp 临时文件（`.part`、`.f*.mp4` 等）
  - 不影响已存在的旧视频文件
- 下载失败的清理：
  - 同上，清理临时文件，不影响旧视频

## 3.5 视频库展示（前端，详见 [01-frontend.md §1.2.3](01-frontend.md)）

## 3.6 搜索与筛选

| 字段 | 支持搜索 | 支持排序 |
|------|----------|----------|
| `title` | ✅（LIKE） | ✅ A-Z |
| `uploader` | ✅ | ✅ |
| `upload_date` | — | ✅ 新→旧 / 旧→新 |
| `duration` | — | ✅ 短→长 / 长→短 |
| `created_at` | — | ✅ |

## 3.7 API 接口

| Method | Path | 用途 |
|--------|------|------|
| GET | `/api/videos` | 列出视频（支持 `q`、`uploader`、`sort`、`page`、`limit`） |
| GET | `/api/videos/{id}` | 视频详情 |
| DELETE | `/api/videos/{id}` | 删除单个视频（同时删除本地文件 + 历史） |
| **POST** | **`/api/videos/batch-delete`** | **批量删除视频**（请求体 `{ ids: [1, 2, ...] }`） |
| GET | `/api/videos/{id}/thumbnail` | 返回缩略图（带本地缓存） |
| GET | `/api/videos/{id}/stream` | 流式播放视频（Range Request 支持） |
| PATCH | `/api/videos/{id}/progress` | 更新播放进度 |
| **POST** | **`/api/downloads/check`** | 检测 URL 是否已在库中（不下载，仅解析） |
| **POST** | **`/api/videos/{id}/redownload`** | 对已有视频发起重下（默认 overwrite=true） |

---

## 3.8 未来扩展（暂不做）

> 以下功能已在 [09-open-questions.md Q6/Q7](09-open-questions.md) 标记为暂缓，仅记录扩展路径。

### 3.8.1 元数据编辑

如未来需要：

- 增加 `PATCH /api/videos/{id}` 接口
- 字段：title、description
- 前端在播放页加"编辑"按钮，弹出表单对话框
- 注意：编辑不影响 file_path，仅改 metadata

### 3.8.2 HLS 分片支持（4K/8K）

- 见 [04-player.md §4.6](04-player.md) 的 4K/8K 未来路线
- 后端在下载完成后调用 `ffmpeg -i input.mp4 -hls_time 6 -hls_list_size 0 output.m3u8`
- 流式接口改为 `/api/videos/{id}/playlist.m3u8`
- 前端播放器切换为 `hls.js`

---

## 3.9 视频删除（已确认 ✅）

> 来源：用户决策"允许用户删除下载的视频，可单删可批量删，删除前弹窗确认"。

### 3.9.1 单个删除

- **API**：`DELETE /api/videos/{id}`
- **后端逻辑**：
  1. 查询视频记录，获取 `file_path`
  2. **先删除本地文件**（即使文件不存在也继续，避免阻塞）
  3. **删除数据库记录**（依赖 SQLite `ON DELETE CASCADE` 自动清理 `play_history`）
  4. 返回 `{ "deleted": true, "id": ... }`

### 3.9.2 批量删除

- **API**：`POST /api/videos/batch-delete`
- **请求体**：`{ "ids": [1, 2, 3, 4] }`
- **后端逻辑**：
  1. 在单个 DB transaction 中查询所有 id 对应的视频记录
  2. **循环删除本地文件**（一个文件失败不中断，记录到 `errors`）
  3. **批量删除数据库记录**（CASCADE 自动清理历史）
  4. 返回响应：
     ```json
     {
       "deleted_count": 3,
       "failed_count": 1,
       "errors": [
         { "id": 4, "reason": "文件被占用：Permission denied" }
       ]
     }
     ```
- **前端**：
  - 弹窗显示选中视频列表（超过 5 个折叠显示）
  - 显示总大小（"X.XX GB"）
  - 删除中显示进度条"删除中 X/N"
  - 部分失败时显示详细 Toast，含失败原因
  - 全部成功显示"已删除 N 个视频"

### 3.9.3 级联清理（已确认）

依赖 SQLite `FOREIGN KEY ... ON DELETE CASCADE`：

```sql
CREATE TABLE play_history (
    ...
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    ...
);
```

- 删除视频时，其所有 `play_history` 记录自动被数据库清理
- 应用层无需手动 DELETE play_history

### 3.9.4 删除保护

- **删除进行中下载任务对应的视频**：禁止（前端需先取消/等待任务完成）
- **删除缩略图缓存**：删除视频时一并删除 `data/thumbnails/{youtube_id}.jpg`
- **删除正在播放的视频**：后端允许删除，但前端应提示用户"该视频正在被播放，请先关闭"

---

## Related

- [00-overview.md](00-overview.md) — 项目总览
- [01-frontend.md](01-frontend.md) — 前端展示细节
- [04-player.md](04-player.md) — 视频流式播放