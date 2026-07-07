# Design 索引

> 本目录是 TubeHub 项目**详细设计文档**的入口。所有设计基于已确认的需求（`../requirements/`）与本地 yt-dlp 集成知识沉淀（`.learnings/`）。

## 文档清单

| 编号 | 文档 | 模块 | 状态 |
|------|------|------|------|
| 00 | [architecture.md](00-architecture.md) | 整体架构 + ADR + 依赖清单 | ✅ |
| 01 | [database-schema.md](01-database-schema.md) | SQLAlchemy 模型 + 索引 + 迁移 | ✅ |
| 02 | [api-design.md](02-api-design.md) | RESTful API + Pydantic Schema | ✅ |
| 03 | [yt-dlp-integration.md](03-yt-dlp-integration.md) | 调度器 + 下载器 + 钩子 + 重试 | ✅ |
| 04 | [frontend-components.md](04-frontend-components.md) | React 组件树 + video.js 集成 | ✅ |
| 05 | [settings-and-config.md](05-settings-and-config.md) | Cookies / Proxy 服务 | ✅ |
| 06 | [error-handling.md](06-error-handling.md) | 错误码体系 + SSE 推送 + 日志 | ✅ |
| 07 | [operations.md](07-operations.md) | 部署 + 启动顺序 + 备份恢复 | ✅ |

## 阅读顺序建议

1. **首次阅读**：[00-architecture.md](00-architecture.md) → [01-database-schema.md](01-database-schema.md)
2. **后端编码**：[02-api-design.md](02-api-design.md) → [03-yt-dlp-integration.md](03-yt-dlp-integration.md) → [05-settings-and-config.md](05-settings-and-config.md) → [06-error-handling.md](06-error-handling.md)
3. **前端编码**：[04-frontend-components.md](04-frontend-components.md)
4. **运维上线**：[07-operations.md](07-operations.md)

## 设计原则

- **最小代码原则**：每个服务文件聚焦单一职责，便于独立测试
- **隔离性**：服务之间通过明确定义的接口（函数签名）通信，不直接访问数据库
- **可观测性**：每个服务都有对应的日志输出，日志分级清晰
- **可演进**：Schema 演进路径已规划，Settings 设计支持新字段平滑添加

## Related

- [`../requirements/`](../requirements/) — 需求文档
- [`../.learnings/`](../../.learnings/) — 技术调研沉淀
- [`../../GEMINI.md`](../../GEMINI.md) — 项目指令准则