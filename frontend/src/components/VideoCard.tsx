/**
 * VideoCard — 视频库单卡片（仿 YouTube 极致美学重构）
 *
 * 包含：
 *  - 16:9 缩略图
 *  - 右下角黑色时长角标 (YouTube 经典)
 *  - 封面底部红色 watch percentage 进度条带 (YouTube 经典)
 *  - 单删与 Checkbox 在 Hover 时在封面左上/右上浮现 Overlay，不占用元信息层
 *  - 扁平整洁的元数据：标题（最多 2 行截断） + 上传者名 + 添加日期
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

// 格式化秒数为 hh:mm:ss / mm:ss
function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return '00:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);

  const mStr = m.toString().padStart(2, '0');
  const sStr = s.toString().padStart(2, '0');

  if (h > 0) {
    return `${h}:${mStr}:${sStr}`;
  }
  return `${m}:${sStr}`;
}

// 格式化入库日期
function formatDate(dateStr?: string): string {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
  } catch {
    return dateStr;
  }
}

export function VideoCard({ video, selected, onSelect, onDelete }: VideoCardProps) {
  const status = useMemo(() => calcStatus(video), [video]);
  const percent = useMemo(() => formatPercent(video), [video]);
  const durationStr = useMemo(
    () => formatDuration(video.duration),
    [video.duration],
  );
  const dateStr = useMemo(() => formatDate(video.created_at), [video.created_at]);

  const thumbnailUrl = `/api/videos/${video.id}/thumbnail`;

  return (
    <div className={`video-card ${selected ? 'video-card--selected' : ''}`}>
      {/* 16:9 比例缩略图容器 */}
      <div className="video-card__thumb-container">
        <Link to={`/watch/${video.id}`} className="video-card__link">
          <img
            className="video-card__thumb"
            src={thumbnailUrl}
            alt={video.title}
            loading="lazy"
          />
        </Link>

        {/* YouTube 经典：右下角时长 */}
        <span className="video-card__duration">{durationStr}</span>

        {/* 状态角标 (🆕 未播放 / ✓ 已看完) */}
        {status !== 'watching' && (
          <span className={`video-card__status-badge video-card__status-badge--${status}`}>
            {status === 'unwatched' && '🆕'}
            {status === 'completed' && '✓'}
          </span>
        )}

        {/* YouTube 经典：底部红色 watch 进度条带 */}
        {status === 'watching' && (
          <div className="video-card__progress-track" title={`已观看 ${percent}%`}>
            <div
              className="video-card__progress-bar"
              style={{ width: `${percent}%` }}
            />
          </div>
        )}

        {/* Hover 浮现的操作 Overlay */}
        <div className="video-card__overlay">
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
            title="删除视频"
          >
            🗑
          </button>
        </div>
      </div>

      {/* 下方元信息（纯净 YouTube 质感） */}
      <div className="video-card__meta">
        <Link to={`/watch/${video.id}`} className="video-card__link">
          <h3 className="video-card__title" title={video.title}>
            {video.title}
          </h3>
        </Link>
        <div className="video-card__info-row">
          {video.uploader && (
            <span className="video-card__uploader">{video.uploader}</span>
          )}
          <span className="video-card__dot-divider">•</span>
          <span className="video-card__date">{dateStr || '刚刚'}</span>
        </div>
      </div>
    </div>
  );
}

export default VideoCard;