# 05. 播放历史需求

> 来源：用户需求 §5

## 5.0 当前代码实现状态（2026-07-11）

- 已实现：`GET /api/history`、`DELETE /api/history/{id}`、`POST /api/history/clear`（支持 `before_days` 参数）。
- `history_cleaner_loop` 已实现，每小时清理 30 天前的历史记录。

## 5.1 核心要求

| 项 | 说明 |
|----|------|
| 记录触发 | 每次播放视频时记录（开始播放 + 进度更新） |
| 去重 | 同一视频多次播放只保留最新一条历史 |
| 排序 | 按 `last_watched_at` 倒序（最近的在最上） |
| 存储 | 独立的 `play_history` 表 |

## 5.2 数据模型

```python
class PlayHistory:
    id: int
    video_id: int              # 外键 → videos.id
    position: float            # 上次播放位置（秒）
    duration: float            # 视频总时长（秒）
    progress_percent: float    # position / duration × 100
    completed: bool            # 是否看完（≥ 95%）
    first_watched_at: datetime # 首次观看时间
    last_watched_at: datetime  # 最近一次观看时间
    watch_count: int           # 累计观看次数
```

## 5.3 行为规则

### 5.3.1 写入时机
- 视频开始播放时（如有进度记忆且 5 秒前未有记录）→ INSERT 或 UPDATE
- 每 30 秒上报一次（避免频繁写库）
- 视频暂停 / 关闭 / 跳转进度 → 立即上报

### 5.3.2 去重策略
- 同一 `video_id` 始终只有一条记录
- 每次播放更新 `last_watched_at`、`position`、`watch_count += 1`
- `first_watched_at` 在首次创建时设定，之后不变

### 5.3.3 "已观看"与"已看完"判定（已确认 ✅）

| 状态 | 条件 | UI 表现 |
|------|------|---------|
| **未播放** | `position == 0` 或 `last_watched_at IS NULL` | 卡片角标显示"🆕 未播放" |
| **已观看** | `position > 5s 且 position < duration × 0.95` | 卡片角标显示"▶️ 已观看" + 当前进度 |
| **已看完** | `position / duration ≥ 0.95` | 卡片角标显示"✓ 已看完" |

- 数据库 `videos.last_position` 字段记录当前观看位置
- 每次播放器上报进度时同步更新
- 角标在视频库首页渲染时根据上述条件实时计算（不存储标志位）

## 5.4 API 接口

| Method | Path | 用途 |
|--------|------|------|
| GET | `/api/history` | 列出历史（支持分页、completed 过滤） |
| POST | `/api/history` | 创建/更新历史条目（播放器上报） |
| DELETE | `/api/history/{id}` | 删除单条历史 |
| POST | `/api/history/clear` | 清空历史（可带 `before_days` 参数） |

## 5.5 前端展示

详见 [01-frontend.md §1.2.5](01-frontend.md)

## 5.6 数据保留策略（已确认 ✅）

| 策略 | 说明 |
|------|------|
| **保留时长** | **30 天**（2026-07-07 决策） |
| 清理方式 | **每日凌晨 3:00 自动清理 30 天前的历史记录**（通过 APScheduler / 后台任务） |
| 手动清理 | 设置页提供"立即清理 30 天前的"按钮（手动触发相同逻辑） |
| 清理范围 | 仅清理 `last_watched_at < now() - 30 days` 的记录 |

### 5.6.1 实现建议

```python
# services/history_cleaner.py
from datetime import datetime, timedelta
from sqlalchemy import delete

async def cleanup_expired_history(session):
    """清理 30 天前的历史记录"""
    cutoff = datetime.utcnow() - timedelta(days=30)
    stmt = delete(PlayHistory).where(PlayHistory.last_watched_at < cutoff)
    result = await session.execute(stmt)
    await session.commit()
    logger.info(f"清理过期历史: 删除 {result.rowcount} 条")
    return result.rowcount
```

### 5.6.2 调度策略

- 使用 **APScheduler**（已在 venv 中预装）注册 cron 任务：`0 3 * * *`
- 或在应用启动时挂载一个 asyncio task 每日执行

---

## 5.7 删除视频时级联清理（已确认 ✅）

> 用户决策：删除视频必须级联清理播放历史中对应记录。

- **机制**：依赖 SQLite 外键约束 `ON DELETE CASCADE`（详见 [03-library.md §3.9.3](03-library.md)）
- **触发时机**：
  - 用户在视频库点击删除单个视频
  - 用户批量删除多个视频
  - 后端自动重新下载并覆盖旧视频（保留旧 video_id）时，**历史不删除**（仅重置 last_position）

### 5.7.1 SQL 定义

```sql
CREATE TABLE play_history (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id          INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    ...
);
```

### 5.7.2 应用层配合

- 删除视频时，应用层**无需**手动 DELETE play_history
- SQLAlchemy 配置：`engine = create_engine(..., connect_args={"check_same_thread": False})`
- SQLite 需启用外键：`PRAGMA foreign_keys = ON;`（每次连接时设置）

---

## Related

- [00-overview.md](00-overview.md) — 项目总览
- [04-player.md](04-player.md) — 播放器上报进度
- [01-frontend.md](01-frontend.md) — 历史页面 UI