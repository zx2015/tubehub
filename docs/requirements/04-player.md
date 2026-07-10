# 04. 播放器需求

> 来源：用户需求 §4

## 4.0 当前代码实现状态（2026-07-10）

- 前端 `VideoPlayer` + `VideoJSPlayer` 组件与基础进度上报逻辑已存在。
- 但后端 `GET /api/videos/{id}`、`GET /api/videos/{id}/stream`、`PATCH /api/videos/{id}/progress` 仍为占位实现。
- 因此播放链路尚未端到端打通；本节其余内容属于目标需求而非已交付能力。

## 4.1 功能清单（强制）

| 功能 | 说明 | 优先级 |
|------|------|--------|
| ▶️ 播放 / ⏸ 暂停 | 空格键切换 | P0 |
| ⏪ 后退 / ⏩ 前进 | 左右方向键，每次 10 秒 | P0 |
| 进度条 | 鼠标点击 / 拖动调整进度 | P0 |
| 时间显示 | `当前 / 总时长` 实时更新 | P0 |
| 倍速 | 0.5x / 0.75x / 1.0x / 1.25x / 1.5x / 2.0x | P0 |
| 音量 | 滑块调节（默认 80%） | P0 |
| 全屏 | 浏览器原生全屏 | P0 |
| **进度记忆** | 重新打开恢复 ±2 秒 | P0 |
| 画中画（PiP） | 浏览器原生 | P2 |
| AirPlay / Chromecast | 浏览器原生 | P2 |

## 4.2 进度记忆实现

### 4.2.1 写入时机

- 每 5 秒上报一次进度到后端
- 视频暂停时立即上报
- 页面 `beforeunload` 时立即上报（同步）
- 视频播放完成（≥ 95%）时标记为"已看完"

### 4.2.2 恢复逻辑

```
进入 /watch/{id}
    │
    ▼
后端 GET /api/videos/{id} 返回 last_position
    │
    ▼
前端播放器加载完成后：
  if last_position > 5 and last_position < duration - 10:
    弹出 Toast："是否从 {mm:ss} 继续观看？"
      ├─ [继续] → player.currentTime = last_position
      └─ [从头开始] → player.currentTime = 0
  else:
    从头播放
```

## 4.3 视频流式播放（已确认 ✅ MVP 方案）

### 4.3.1 流式协议

**MVP 方案**：直接使用浏览器原生 `<video>` 标签，请求后端 `GET /api/videos/{id}/stream` 即可。

- 后端使用 FastAPI `FileResponse` + `Range` 请求头支持（FastAPI 自动处理）
- 支持 `Range: bytes=xxx-xxx` 部分内容请求（拖动进度条所需）
- 支持 1080p 及以下视频流畅播放（4K/8K 暂不考虑，详见 [§4.6](#46-4k8k-未来路线)）

### 4.3.2 视频容器兼容性

| 容器 | 浏览器支持 | 备注 |
|------|------------|------|
| MP4 (H.264 + AAC) | ✅ 全部 | **首选格式**，下载时尽量选 |
| WebM (VP9 + Opus) | ✅ 主流 | 1080p 时常见 |
| MKV | ⚠️ Chrome 不支持 | 下载时尽量避免 |

### 4.3.3 HLS 决策（已确认 ✅ 不做）

- 用户决策：MVP 不做 HLS 分片，暂不考虑 4K/8K 大视频下载
- 未来如支持 4K/8K，见 [§4.6](#46-4k8k-未来路线)

## 4.4 播放器选型（已确认 ✅）

> 决策（2026-07-07）：**video.js 8.x** —— 自带进度记忆、倍速、全屏、键盘快捷键控制条，省去自研 UI。

| 候选 | 评估 |
|------|------|
| 原生 `<video>` 标签 + 自定义控制条 | ❌ 不选：跨浏览器 UI 行为不一致，进度记忆/倍速/全屏需手写 ~200 行 |
| **video.js 8.x** | ✅ **已选**：功能齐全、主题适配深色、社区活跃、~200KB gzipped |
| Plyr | ❌ 不选：高级功能薄弱 |
| hls.js | ❌ 不选：仅支持 HLS，与 MVP 不做 HLS 决策冲突 |

### 4.4.1 集成方式

```bash
npm install video.js@^8 @types/video.js
```

```tsx
import videojs from 'video.js';
import 'video.js/dist/video-js.css';

const player = videojs(el, {
    controls: true,
    autoplay: false,
    preload: 'auto',
    fluid: true,                    // 自适应容器
    playbackRates: [0.5, 0.75, 1, 1.25, 1.5, 2],
    controlBar: {
        pictureInPictureToggle: true,
    },
});
player.src({ src: `/api/videos/${id}/stream`, type: 'video/mp4' });

// 进度上报（每 5 秒）
let lastReportPos = 0;
player.on('timeupdate', () => {
    const pos = player.currentTime();
    if (Math.abs(pos - lastReportPos) >= 5) {
        fetch(`/api/videos/${id}/progress`, {
            method: 'PATCH',
            body: JSON.stringify({ position: pos }),
        });
        lastReportPos = pos;
    }
});

// 暂停 / 卸载前强制上报
player.on('pause', () => reportProgress());
window.addEventListener('beforeunload', () => {
    navigator.sendBeacon(`/api/videos/${id}/progress`,
        JSON.stringify({ position: player.currentTime() }));
});
```

## 4.5 播放页布局

```
┌─────────────────────────────────────────┐
│  [返回 ←]  视频标题                       │
├─────────────────────────────────────────┤
│                                         │
│         [视频播放器 16:9]                │
│                                         │
├─────────────────────────────────────────┤
│  标题：xxx                               │
│  上传者：xxx  时长：mm:ss  画质：1080p     │
│  描述：（可折叠）                         │
├─────────────────────────────────────────┤
│  操作：[重新下载] [删除] [复制 YouTube 链接]│
└─────────────────────────────────────────┘
```

## 4.6 4K/8K 未来路线（已记录，暂不做）

> 用户决策（2026-07-07）：**暂不支持 4K/8K 视频下载**，故 MVP 不实现 HLS 分片。
> 此小节记录未来如支持 4K/8K 大视频的扩展路径。

### 4.6.1 触发条件

未来若决定支持 4K/8K，建议同时引入：

1. **HLS 自适应分片**：将 MP4 转码为 `.m3u8` + `.ts` 切片
2. **码率自适应**：根据用户带宽自动选择清晰度

### 4.6.2 技术方案

#### 后端

- 下载完成后异步调用 FFmpeg：
  ```bash
  ffmpeg -i input.mp4 \
         -codec: copy \
         -start_number 0 \
         -hls_time 6 \
         -hls_list_size 0 \
         -f hls \
         output.m3u8
  ```
- 生成路径：`data/videos/{uploader}/{title}[{id}]/playlist.m3u8` + segments/
- 数据库新增字段：`hls_path`（指向 m3u8）

#### 流式接口变化

- 新增 `GET /api/videos/{id}/playlist.m3u8`（返回 m3u8 索引）
- 新增 `GET /api/videos/{id}/segments/{segment}`（返回切片）
- 保留 `GET /api/videos/{id}/stream`（MP4 直接流式，作为兜底）

#### 前端

- 引入 `hls.js`
- 播放器自动检测：
  - 若 `video.hls_path` 存在 → 使用 hls.js
  - 否则 → 使用原生 `<video>` + MP4 流式

### 4.6.3 待评估权衡

| 权衡点 | 说明 |
|--------|------|
| 磁盘占用 | HLS 切片会复制视频内容，约增加 5-10% 磁盘 |
| 转码耗时 | 4K 视频 FFmpeg 转码可能需要数分钟 |
| 切片粒度 | 建议 6 秒一片（用户体验与文件数平衡） |
| 缓存策略 | 已观看过的不再重新转码（依赖数据库标记） |

### 4.6.4 关联文档

- [03-library.md §3.8.2 HLS 分片支持](03-library.md) — 数据库与 API 扩展
- [02-downloader.md §2.2.2 清晰度](02-downloader.md) — 4K/8K 清晰度选项

---

## Related

- [00-overview.md](00-overview.md) — 项目总览
- [01-frontend.md](01-frontend.md) — 前端展示
- [03-library.md](03-library.md) — 视频元数据