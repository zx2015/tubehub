# 04. 前端组件设计

> 技术栈：React 18 + Vite + TypeScript + Vanilla CSS + video.js 8.x

## 4.1 路由设计

| Path | 组件 | 说明 |
|------|------|------|
| `/` | `<VideoLibrary />` | 视频库首页（网格 + 搜索 + 排序 + 批量删除） |
| `/downloads` | `<DownloadTasks />` | 下载任务列表（含 SSE 进度） |
| `/watch/:id` | `<VideoPlayer />` | 视频播放页 |
| `/settings` | `<Settings />` | 设置（Cookies + Proxy + 清理） |

## 4.2 组件树

```
<App>
├── <Layout>                     // 顶部导航栏 + 路由出口
│   ├── <NavBar />               // Logo + 三个路由入口 + 设置图标
│   └── <Routes>
│       ├── <VideoLibrary />
│       │   ├── <Toolbar />              // 搜索框、排序、新增下载
│       │   ├── <BatchActionBar />       // 选中 ≥1 项时显示
│       │   ├── <VideoGrid>
│       │   │   └── <VideoCard />        // hover 显示多选 + 删除
│       │   ├── <AddDownloadDialog />    // + 添加下载对话框
│       │   └── <ConfirmDialog />        // 单删 / 批量删确认
│       ├── <DownloadTasks />
│       │   ├── <TaskRow />              // 每行任务 + SSE 进度
│       │   └── <BatchCleanBar />
│       ├── <VideoPlayer />
│       │   ├── <VideoJSPlayer />        // 包装 video.js
│       │   └── <VideoMeta />            // 标题/上传者/操作按钮
│       └── <Settings />
│           ├── <CookiesSection />
│           └── <ProxySection />
```

## 4.3 状态管理

本项目**不使用 Redux/Zustand**，使用 React 内置 hooks + 自定义 hook 拆分。

### 4.3.1 自定义 Hooks

| Hook | 文件 | 职责 |
|------|------|------|
| `useSSE` | `hooks/useSSE.ts` | 订阅 SSE，自动重连，组件卸载时关闭 |
| `useTaskProgress` | `hooks/useTaskProgress.ts` | 包装 useSSE，返回 task 当前状态 |
| `useVideos` | `hooks/useVideos.ts` | 视频列表的查询、排序、过滤、批量删除 |
| `useSettings` | `hooks/useSettings.ts` | Cookie 与 Proxy 状态读写 |

### 4.3.2 useSSE 示例

```typescript
// hooks/useSSE.ts
export function useSSE<T>(url: string, onMessage: (data: T) => void) {
  useEffect(() => {
    const es = new EventSource(url);
    es.onmessage = (e) => onMessage(JSON.parse(e.data));
    es.onerror = () => {
      // EventSource 自动重连，但显式记录日志
      console.warn(`SSE disconnected: ${url}`);
    };
    return () => es.close();
  }, [url]);
}
```

## 4.4 VideoCard 设计

```typescript
interface VideoCardProps {
  video: VideoRead;
  selected: boolean;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
}

export function VideoCard({ video, selected, onSelect, onDelete }: VideoCardProps) {
  // 已观看 / 已看完角标判定（需求 05 §5.3.3）
  const status = useMemo(() => {
    if (video.last_position === 0) return 'unwatched';
    if (video.last_position >= video.duration * 0.95) return 'completed';
    if (video.last_position > 5) return 'watching';
    return 'unwatched';
  }, [video.last_position, video.duration]);

  return (
    <div className={`video-card ${selected ? 'selected' : ''}`}>
      {/* hover 时显示多选 + 删除 */}
      <input type="checkbox" className="select-checkbox"
             checked={selected} onChange={() => onSelect(video.id)} />
      <button className="delete-btn" onClick={() => onDelete(video.id)}>🗑</button>

      <Link to={`/watch/${video.id}`}>
        <img src={`/api/videos/${video.id}/thumbnail`} alt={video.title} />
        <span className={`status-badge status-${status}`}>
          {status === 'unwatched' && '🆕'}
          {status === 'watching' && `${Math.round(video.last_position / video.duration * 100)}%`}
          {status === 'completed' && '✓'}
        </span>
        <h3>{video.title}</h3>
      </Link>
    </div>
  );
}
```

## 4.5 VideoJSPlayer 设计（关键集成）

```typescript
// components/VideoJSPlayer.tsx
import videojs from 'video.js';
import 'video.js/dist/video-js.css';
import { useEffect, useRef } from 'react';

interface Props {
  src: string;
  startPosition?: number;        // 进度记忆的恢复位置
  onProgress: (position: number) => void;
}

export function VideoJSPlayer({ src, startPosition = 0, onProgress }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<any>(null);
  const lastReportRef = useRef<number>(0);

  useEffect(() => {
    if (!containerRef.current) return;

    const videoEl = document.createElement('video-js');
    videoEl.classList.add('vjs-big-play-centered', 'vjs-fluid');
    containerRef.current.appendChild(videoEl);

    const player = playerRef.current = videojs(videoEl, {
      controls: true,
      autoplay: false,
      preload: 'auto',
      playbackRates: [0.5, 0.75, 1, 1.25, 1.5, 2],
      sources: [{ src, type: 'video/mp4' }],
    });

    // 元数据加载完成后跳转到上次位置
    player.on('loadedmetadata', () => {
      if (startPosition > 5 && startPosition < player.duration()! - 10) {
        player.currentTime(startPosition);
      }
    });

    // 进度上报（每 5 秒一次）
    player.on('timeupdate', () => {
      const pos = player.currentTime()!;
      if (Math.abs(pos - lastReportRef.current) >= 5) {
        onProgress(pos);
        lastReportRef.current = pos;
      }
    });

    // 暂停时强制上报
    player.on('pause', () => onProgress(player.currentTime() || 0));

    return () => player.dispose();
  }, [src]);

  // 卸载前最后一次上报
  useEffect(() => {
    return () => {
      const pos = playerRef.current?.currentTime();
      if (pos) onProgress(pos);
    };
  }, []);

  return <div ref={containerRef} className="video-js-container" />;
}
```

## 4.6 数据流：用户播放视频

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户
    participant Page as VideoPlayer 页
    participant VJS as video.js
    participant API as FastAPI

    User->>Page: 点击视频卡片
    Page->>API: GET /api/videos/{id}
    API-->>Page: 返回 video (含 last_position)
    Page->>VJS: 初始化 + sources
    VJS->>API: GET /api/videos/{id}/stream (Range)
    API-->>VJS: 视频字节流
    VJS->>VJS: loadedmetadata
    VJS->>VJS: currentTime(last_position)
    loop 播放中
        VJS->>Page: timeupdate event
        Page->>API: PATCH /api/videos/{id}/progress (每 5s)
    end
    User->>VJS: 关闭页面
    VJS->>Page: 卸载
    Page->>API: PATCH /progress (最后一次)
```

## 4.7 AddDownloadDialog 流程

```typescript
const handleAddDownload = async (url: string, quality: string) => {
  // 1. 前置 check
  const check = await fetch('/api/downloads/check', {
    method: 'POST',
    body: JSON.stringify({ url })
  }).then(r => r.json());

  if (check.conflict) {
    // 2. 弹出覆盖确认
    const confirmed = await openConfirmDialog({
      title: '视频已存在',
      message: `《${check.existing_video.title}》已在库中。是否覆盖？`,
    });
    if (!confirmed) return;
  }

  // 3. 提交任务
  await fetch('/api/downloads', {
    method: 'POST',
    body: JSON.stringify({
      url, quality,
      overwrite: check.conflict && confirmed,
    }),
  });

  toast.success('下载任务已添加');
};
```

## 4.8 样式组织

```
frontend/src/styles/
├── reset.css            // CSS reset
├── theme.css            // 设计变量（颜色、间距）
├── layout.css           // 顶部导航、容器布局
├── VideoCard.css
├── AddDownloadDialog.css
├── ConfirmDialog.css
├── VideoPlayer.css
├── Settings.css
└── ...
```

CSS Modules 或纯 BEM 命名规范任选其一，本设计推荐 **BEM**（保持极简）。

---

## Related

- [00-architecture.md](00-architecture.md) — 整体架构
- [02-api-design.md](02-api-design.md) — API 签名