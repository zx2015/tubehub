/**
 * VideoCard — 视频库单卡片
 *
 * 设计依据：docs/design/04-frontend-components.md §4.4
 *
 * 行为：
 *  - 缩略图 + 标题 + 状态角标
 *  - hover 时显示多选 checkbox 与删除按钮
 *  - 点击卡片跳转到 /watch/:id
 */
import { Link } from 'react-router-dom';
import { useMemo } from 'react';
import type { VideoRead } from '../types';

interface VideoCardProps {
  video: VideoRead;
  selected: boolean;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
}

type PlaybackStatus = 'unwatched' | 'watching' | 'completed';

function calcStatus(video: VideoRead): PlaybackStatus {
  if (!video.last_position || video.last_position <= 0) return 'unwatched';
  const duration = video.duration ?? 0;
  if (duration > 0 && video.last_position >= duration * 0.95) return 'completed';
  if (video.last_position > 5) return 'watching';
  return 'unwatched';
}

function formatPercent(video: VideoRead): number {
  const duration = video.duration ?? 0;
  if (!duration) return 0;
  return Math.min(100, Math.round((video.last_position / duration) * 100));
}

export function VideoCard({ video, selected, onSelect, onDelete }: VideoCardProps) {
  const status = useMemo(() => calcStatus(video), [video]);
  const percent = useMemo(() => formatPercent(video), [video]);

  const thumbnailUrl = `/api/videos/${video.id}/thumbnail`;

  return (
    <div className={`video-card ${selected ? 'video-card--selected' : ''}`}>
      <input
        type="checkbox"
        className="video-card__checkbox"
        checked={selected}
        onChange={() => onSelect(video.id)}
        aria-label={`选择 ${video.title}`}
      />
      <button
        type="button"
        className="video-card__delete"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onDelete(video.id);
        }}
        aria-label="删除视频"
        title="删除"
      >
        🗑
      </button>

      <Link to={`/watch/${video.id}`} className="video-card__link">
        <div className="video-card__thumb">
          <img src={thumbnailUrl} alt={video.title} loading="lazy" />
          <span className={`video-card__badge video-card__badge--${status}`}>
            {status === 'unwatched' && '🆕'}
            {status === 'watching' && `${percent}%`}
            {status === 'completed' && '✓'}
          </span>
        </div>
        <h3 className="video-card__title" title={video.title}>
          {video.title}
        </h3>
        {video.uploader && (
          <p className="video-card__meta">{video.uploader}</p>
        )}
      </Link>
    </div>
  );
}

export default VideoCard;