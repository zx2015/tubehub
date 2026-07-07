# 09. 待澄清问题汇总

> 本文档汇总所有未明确的需求点，供后续会话查阅。
> **当前状态**：所有阻塞 MVP 启动的问题已全部确认 ✅。本文档主要为历史归档与未来扩展参考。

## 目录

- [9.1 已确认决策清单（历史归档）](#91-已确认决策清单历史归档)
- [9.2 待澄清问题](#92-待澄清问题)

---

## 9.1 已确认决策清单（历史归档）

> 所有确认日期：2026-07-07。
> 这些决策的细节已分别同步至对应模块文档，本节仅作索引，便于跨文档检索。

| # | 决策 | 取值 | 落地位置 |
|---|------|------|----------|
| Q1 | 前端框架 | React 18 + Vite + TypeScript + Vanilla CSS | [01-frontend.md §1.4](01-frontend.md) |
| Q2 | 歌单下载行为 | 串行下载 + 任务列表扁平展示（不分组） | [02-downloader.md §2.2.3](02-downloader.md) |
| Q3 | 重新下载行为 | 默认覆盖 + 前置 check + 弹窗确认 | [03-library.md §3.4](03-library.md) |
| Q4 | 视频文件命名 | `{uploader}/{title}[{youtube_id}].{ext}` | [03-library.md §3.3](03-library.md) |
| Q5 | 失败重试策略 | 自动重试 3 次后置为 Failed，可手动重启 | [02-downloader.md §2.8](02-downloader.md) |
| Q5+ | 任务并发上限 | 最多 2 个并行，超出 queued FIFO | [02-downloader.md §2.2.3](02-downloader.md) |
| Q6 | HLS 分片（4K/8K） | MVP 不做，记录未来路线 | [04-player.md §4.6](04-player.md) |
| Q7 | 元数据编辑 | MVP 不做（仅展示） | [03-library.md §3.8.1](03-library.md) |
| Q8 | 历史保留策略 | 30 天自动清理（仅 play_history） | [05-history.md §5.6](05-history.md) |
| Q9 | 自建播放列表 | 不做 | [01-frontend.md §1.5](01-frontend.md) |
| Q12 | HTTPS | 不做（内网） | [08-deployment.md](08-deployment.md) |
| Q13 | CI/CD | 不做（个人项目） | — |
| Q14 | 反向代理 | 可选（文档示例） | [08-deployment.md](08-deployment.md) |
| Q16 | 国际化 i18n | 不做 | — |
| Q19 | yt-dlp Cookies | 设置页支持上传/配置/清除 | [07-backend.md §7.3.1](07-backend.md) |
| Q20 | 推送 GHCR | 不推送，用户自行 build | — |
| Q21 | 部署模式（内网） | 无认证、无登录页 | [06-auth.md](06-auth.md) |
| Q22 | 删除视频级联清理 | SQL `ON DELETE CASCADE` | [03-library.md §3.9.3](03-library.md) |
| Q23 | 视频删除 UI | 单删 + 批量删 + 确认弹窗 | [03-library.md §3.9](03-library.md) |
| Q24 | 下载代理配置 | HTTP/HTTPS/SOCKS5，可测试连通性 | [07-backend.md §7.3.2](07-backend.md) |
| **N1** | **前端播放器** | **video.js 8.x** | **[04-player.md §4.4](04-player.md)** |
| **N2** | **调度器实现** | **`asyncio.create_task` 循环 + `Semaphore(2)`** | **[02-downloader.md §2.2.3](02-downloader.md)** |
| **N3** | **音频格式** | **裁切，不支持"仅音频"下载** | **[02-downloader.md §2.2.1](02-downloader.md)** |
| **N4** | **已观看阈值** | **`position > 5s 且 < duration × 0.95`** | **[05-history.md §5.3.3](05-history.md)** |
| **N5** | **视频库默认排序** | **最新添加优先（`created_at DESC`）** | **[01-frontend.md §1.2.3](01-frontend.md)** |
| **N6** | **字幕支持** | **不做字幕** | **[04-player.md §4.1](04-player.md)** |
| **N7** | **任务记录保留期** | **Ready 3 天 / Failed & Cancelled 30 天** | **[02-downloader.md §2.9](02-downloader.md)** |
| **N8** | **自动重试上限** | **自动 3 次后转 Failed，可手动重启** | **[02-downloader.md §2.8](02-downloader.md)** |
| **N9** | **缩略图下载** | **必须下载到本地，且必须走代理** | **[03-library.md §3.1.2](03-library.md)** |

> 技术栈细节（后端 Python/FastAPI/SQLite/yt-dlp/FFmpeg、缩略图来源、进度推送 SSE、容器 MP4、流式 Range）已在 [00-overview.md](00-overview.md) 与 [07-backend.md](07-backend.md) 统一记录，不再在本表重复。

---

## 9.2 待澄清问题

> **当前**：所有 P0/P1 阻塞性问题已全部确认。本节仅作为未来扩展或细化讨论的占位。
> 如需发起新的澄清项，请按以下格式追加并明确标注 P0/P1/P2。

### P2 - 可延后讨论

| # | 问题 | 状态 | 默认方案 / 说明 |
|---|------|------|----------------|
| F1 | 是否需要在播放页显示视频的章节信息（chapter）？ | ⏳ | yt-dlp 可解析 chapters 字段但未使用；如需，扩展 `videos.chapters_json` 字段 |
| F2 | 下载任务列表是否支持筛选（按状态、上传者）？ | ⏳ | 当前为扁平列表，可后续扩展 |
| F3 | 是否提供 RESTful OpenAPI 文档？ | ⏳ | 默认启用 FastAPI `/docs` Swagger |
| F4 | 失败任务的 `error_message` 是否暴露给前端？ | ⏳ | 建议截取前 200 字符展示，避免泄露敏感信息 |

---

## 相关文档

- [00-overview.md](00-overview.md) — 项目总览与技术栈
- [02-downloader.md](02-downloader.md) — 下载功能详细需求
- [03-library.md](03-library.md) — 视频库与缩略图
- [04-player.md](04-player.md) — 播放器详细需求
- [05-history.md](05-history.md) — 播放历史
- [07-backend.md](07-backend.md) — 后端架构
- [08-deployment.md](08-deployment.md) — 部署指南

## Related

- [`../GEMINI.md`](../../GEMINI.md) — 项目指令准则
- [`.learnings/knowledge/yt-dlp-integration.md`](../../.learnings/knowledge/yt-dlp-integration.md) — yt-dlp 集成知识沉淀