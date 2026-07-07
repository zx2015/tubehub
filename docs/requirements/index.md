# Requirements 索引

> 本目录是 TubeHub 项目模块化需求文档的入口。所有需求按业务域拆分，每个文档聚焦于一个子系统。

## 文档清单

| 编号 | 文档 | 模块 | 优先级 | 状态 |
|------|------|------|--------|------|
| 00 | [overview.md](00-overview.md) | 项目总览、技术栈、范围边界 | — | ✅ |
| 01 | [frontend.md](01-frontend.md) | 前端 UI 与交互 | P0 | ✅ |
| 02 | [downloader.md](02-downloader.md) | YouTube 下载任务与进度 | P0 | ✅ |
| 03 | [library.md](03-library.md) | 视频库与缩略图 | P0 | ✅ |
| 04 | [player.md](04-player.md) | Web 播放器与进度记忆 | P0 | ✅ |
| 05 | [history.md](05-history.md) | 播放历史 | P0 | ✅ |
| 06 | [auth.md](06-auth.md) | 单用户认证 | P0 | ✅ |
| 07 | [backend.md](07-backend.md) | 后端 API、数据库、异步任务 | P0 | ✅ |
| 08 | [deployment.md](08-deployment.md) | 本地 venv 运行与 Docker 部署 | P0 | ✅ |
| 09 | [open-questions.md](09-open-questions.md) | **待澄清问题汇总** | — | ⏳（P0 已全部确认，仅余 P1/P2） |

## 阅读顺序建议

1. 首次阅读：[00-overview.md](00-overview.md) → [09-open-questions.md](09-open-questions.md)
2. 编码前：✅ P0 问题（Q1-Q5+）已全部确认；可继续推进 P1（Q6-Q11）
3. 开发期：按模块依次实现，对应章节阅读

## 维护规则

- 新增需求文档时，立即更新本索引
- 状态变化（确认/废弃）时同步更新
- 文档之间通过相对路径建立互联（见各文档末尾的 `## Related`）

---

## Related

- [`../design/`](../design/) — 设计文档（待创建）
- [`../GEMINI.md`](../../GEMINI.md) — 项目指令准则