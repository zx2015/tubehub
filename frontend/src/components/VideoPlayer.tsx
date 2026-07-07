/**
 * VideoPlayer — /watch/:id 播放页
 *
 * 设计依据：docs/design/04-frontend-components.md §4.5/4.6
 *
 * 行为：
 *  - 通过 useParams 拿到视频 id
 *  - 拉取视频元数据（GET /api/videos/{id}）拿到 last_position
 *  - 用 VideoJSPlayer 渲染播放器，src 指向 /api/videos/{id}/stream
 *  - 进度上报（PATCH /api/videos/{id}/progress）由 VideoJSPlayer.onProgress 触发
 */
import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import VideoJSPlayer from './VideoJSPlayer';
import type { VideoRead } from '../types';

export function VideoPlayer() {
  const { id } = useParams<{ id: string }>();
  const videoId = Number(id);
  const [meta, setMeta] = useState<VideoRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isFinite(videoId)) {
      setError('非法视频 ID');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    fetch(`/api/videos/${videoId}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return (await r.json()) as VideoRead;
      })
      .then((data) => setMeta(data))
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : String(err)),
      )
      .finally(() => setLoading(false));
  }, [videoId]);

  const handleProgress = useCallback(
    async (position: number) => {
      if (!Number.isFinite(videoId)) return;
      try {
        await fetch(`/api/videos/${videoId}/progress`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ position, duration: meta?.duration ?? 0 }),
          keepalive: true,
        });
      } catch {
        // 静默失败：进度上报不影响播放
      }
    },
    [videoId, meta?.duration],
  );

  if (loading) {
    return <div className="video-player__status">加载视频信息…</div>;
  }
  if (error) {
    return (
      <div className="video-player__status video-player__status--error">
        加载失败：{error}
        <div>
          <Link to="/" className="btn btn--ghost">
            返回视频库
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="video-player">
      <div className="video-player__header">
        <Link to="/" className="btn btn--ghost">
          ← 返回
        </Link>
        <h1 className="video-player__title">{meta?.title ?? `视频 #${videoId}`}</h1>
        {meta?.uploader && (
          <span className="video-player__uploader">{meta.uploader}</span>
        )}
      </div>
      <div className="video-player__stage">
        <VideoJSPlayer
          src={`/api/videos/${videoId}/stream`}
          startPosition={meta?.last_position ?? 0}
          onProgress={handleProgress}
        />
      </div>
    </div>
  );
}

export default VideoPlayer;