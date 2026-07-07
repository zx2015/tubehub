# TubeHub 需求文档

> 本目录包含 TubeHub 项目的模块化需求文档。每个文档聚焦于一个功能子系统。

## 目录

| 文档 | 模块 | 状态 |
|------|------|------|
| [00-overview.md](00-overview.md) | 项目总览、技术栈、范围边界 | ✅ 已确认（总览） |
| [01-frontend.md](01-frontend.md) | 前端 UI 与交互 | ✅ 已确认 |
| [02-downloader.md](02-downloader.md) | YouTube 下载任务与进度 | ✅ 已确认 |
| [03-library.md](03-library.md) | 视频库与缩略图 | ✅ 已确认 |
| [04-player.md](04-player.md) | Web 播放器与进度记忆 | ✅ 已确认 |
| [05-history.md](05-history.md) | 播放历史 | ✅ 已确认 |
| [06-auth.md](06-auth.md) | 单用户认证 | ✅ 已确认 |
| [07-backend.md](07-backend.md) | 后端 API、数据库、异步任务 | ✅ 已确认 |
| [08-deployment.md](08-deployment.md) | 本地 venv 运行与 Docker 部署 | ✅ 已确认 |
| [**09-open-questions.md**](09-open-questions.md) | **待澄清问题汇总（必读）** | ⏳ P1/P2 待确认（P0 已全部确认 ✅） |

---

## 0. 项目总览

### 0.1 愿景
TubeHub 是一个**单用户**的私有化 YouTube 视频下载与在线播放平台。所有数据（视频文件、元数据、播放历史）均存储在本地。

### 0.2 技术栈（已确认）

| 层级 | 选型 | 说明 |
|------|------|------|
| 前端 | **React 18 + Vite + TypeScript + Vanilla CSS** ✅ 已确认 | 见 [01-frontend.md](01-frontend.md) |
| 后端框架 | **Python 3.12 + FastAPI** | venv 路径 `/media/data/venv` |
| 异步运行时 | **FastAPI BackgroundTasks**（MVP）或 Celery（生产） | 见 [07-backend.md](07-backend.md) |
| 下载引擎 | **yt-dlp**（Python 模块，非 CLI 调用） | 已在 requirements.txt |
| 数据库 | **SQLite** | 单文件，路径 `data/tubehub.db` |
| 媒体处理 | **FFmpeg**（系统已装 8.1.2） | 用于音视频合并 |
| 认证 | **无认证（内网部署）** | 所有 API 直接开放 |
| 部署 | **venv 本地运行 + Docker Compose（内网）** | 见 [08-deployment.md](08-deployment.md) |

### 0.3 范围边界（In-Scope / Out-of-Scope）

**In-Scope**：
- YouTube 视频/歌单的解析与下载
- 4K/8K 高画质下载与音视频合并（4K/8K 后续优化，详见 [04-player.md §4.6](04-player.md)）
- Web 端 MP4 直接流式播放（基于 video.js 8.x）
- 播放进度记忆、倍速、拖拽
- 播放历史记录（30 天保留 + 自动清理）
- 视频库扁平展示，支持搜索、排序（默认：最新添加优先）、单删、批量删
- 删除视频时级联清理对应播放历史
- 缩略图**走代理下载到本地**进行持久化缓存
- 下载任务**失败自动重试 3 次**，超时后显示为 Failed 并可手动重启
- 下载任务记录**自动清理**（Ready 保留 3 天，Failed/Cancelled 保留 30 天）
- 内网部署，**无需登录**

**Out-of-Scope**（明确不做）：
- ❌ 多用户、注册、权限分级
- ❌ 用户登录（内网部署，所有功能直接开放）
- ❌ 第三方账号登录（OAuth）
- ❌ 评论、点赞、社交分享
- ❌ 移动 App（仅 Web）
- ❌ YouTube 以外平台（Bilibili、Vimeo 等）
- ❌ 云端同步、远程访问
- ❌ 自建播放列表
- ❌ 元数据编辑（用户不可修改标题/描述/标签）
- ❌ HLS 分片（暂不支持 4K/8K 大视频流式）
- ❌ **仅音频下载**（专攻视频下载，不提供 mp3/m4a 等纯音频提取）
- ❌ **字幕**（不下载、不展示外挂字幕）

### 0.4 关键约束

| 约束 | 取值 | 来源 |
|------|------|------|
| 用户数 | 1（单用户） | 需求 §6 |
| 后端语言 | Python | 需求 §6 |
| 下载库 | yt-dlp | 需求 §6 |
| 数据库 | SQLite | 需求 §7 |
| 本地运行 venv | `/media/data/venv` | 需求 §9 |
| 部署 | Docker + Docker Compose | 需求 §10 |

---

## Related

- [`../design/`](../design/) — 设计文档（待创建）
- [`../../TODO.md`](../../TODO.md) — 项目待办事项
- [`../../GEMINI.md`](../../GEMINI.md) — 项目指令准则