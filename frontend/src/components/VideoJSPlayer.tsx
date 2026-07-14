import videojs from 'video.js';
import 'video.js/dist/video-js.css';
import type Player from 'video.js/dist/types/player';
import { useEffect, useRef } from 'react';

interface Props {
  src: string;
  /** 进度记忆的恢复位置（秒） */
  startPosition?: number;
  /** 进度上报回调（秒） */
  onProgress: (position: number) => void;
}

/**
 * VideoJSPlayer
 *
 * TubeHub 视频播放核心包装层，基于 video.js 8.x。
 *
 * 功能要点（与 docs/design/04-frontend-components.md §4.5 完全一致）：
 *  1. loadedmetadata → 恢复 last_position（仅在合理区间内生效，避免越界）
 *  2. timeupdate 每 ≥5 秒触发一次 PATCH 上报
 *  3. pause 触发强制上报
 *  4. 组件卸载前最后一次上报，并通过 beforeunload + sendBeacon 兜底
 *
 *  说明：
 *  - 视频源使用 /api/videos/{id}/stream，由后端以 HTTP Range 提供字节流。
 *  - video.js 8 中直接传入 <video-js> 自定义元素即可，无需手写 <video>。
 */
export function VideoJSPlayer({ src, startPosition = 0, onProgress }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const playerRef = useRef<Player | null>(null);
  const lastReportRef = useRef<number>(0);

  // 主 effect：创建 player，绑定事件，src 变化时整体重建
  useEffect(() => {
    if (!containerRef.current) return;

    // 1. 自定义元素 video-js 由 video.js 注册，这里动态创建并挂载
    const videoEl = document.createElement('video-js');
    videoEl.classList.add('vjs-big-play-centered');
    // 不用 vjs-fluid，改为 fill 模式充满父容器，由 CSS 控制尺寸
    containerRef.current.appendChild(videoEl);

    // 2. 实例化 video.js 播放器
    const player = videojs(videoEl, {
      controls: true,
      autoplay: false,
      preload: 'auto',
      playbackRates: [0.5, 0.75, 1, 1.25, 1.5, 2],
      sources: [{ src, type: 'video/mp4' }],
      fill: true,   // 充满父容器（替代 fluid）
    });

    playerRef.current = player;

    // 3. 元数据加载完成后跳转到上次位置（仅在合理区间）
    player.on('loadedmetadata', () => {
      const duration = player.duration() ?? 0;
      if (startPosition > 5 && startPosition < duration - 10) {
        player.currentTime(startPosition);
      }
      lastReportRef.current = startPosition;
    });

    // 4. 进度上报：每 ≥5 秒一次
    player.on('timeupdate', () => {
      const pos = player.currentTime() ?? 0;
      if (Math.abs(pos - lastReportRef.current) >= 5) {
        onProgress(pos);
        lastReportRef.current = pos;
      }
    });

    // 5. 暂停时强制上报一次
    player.on('pause', () => {
      const pos = player.currentTime() ?? 0;
      onProgress(pos);
      lastReportRef.current = pos;
    });

    // 卸载时释放资源
    return () => {
      player.dispose();
      playerRef.current = null;
    };
  }, [src, startPosition, onProgress]);

  // 卸载前最后一次上报（覆盖组件被销毁但未触发 pause 的情况）
  useEffect(() => {
    const handleBeforeUnload = () => {
      const player = playerRef.current;
      if (!player) return;
      const pos = player.currentTime() ?? 0;
      // sendBeacon 兜底：浏览器关闭/刷新时仍能发出请求
      try {
        if (navigator.sendBeacon && src) {
          // 通过 query 携带 src 与 pos，由后端解析（设计文档 4.6 兜底协议）
          const blob = new Blob(
            [JSON.stringify({ position: pos })],
            { type: 'application/json' },
          );
          navigator.sendBeacon(`${src}/progress`, blob);
        } else {
          onProgress(pos);
        }
      } catch {
        onProgress(pos);
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      const player = playerRef.current;
      if (player) {
        const pos = player.currentTime() ?? 0;
        onProgress(pos);
      }
    };
  }, [onProgress, src]);

  return <div ref={containerRef} className="video-js-container" data-vjs-player />;
}

export default VideoJSPlayer;