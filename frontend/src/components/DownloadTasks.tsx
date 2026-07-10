/**
 * DownloadTasks — 下载任务列表（内置单行 UI + 经典悬浮对话窗口挂载）
 *
 * 设计依据：docs/design/04-frontend-components.md §4.2 + 用户 2026-07-07 决策
 *
 * 功能：
 *  - 任务信息单行显示：标题 / 链接 / 进度 / 状态 / 操作 (🔄 重试、❌ 取消、🗑 删除图标)
 *  - 顶部常驻 [+ 新增下载] 按钮，用于激活真正浮动在页面最上层的独立交互窗口
 */
import { useCallback, useEffect, useState } from 'react';
import { useApi } from '../hooks/useApi';
import { useSSE } from '../hooks/useSSE';
import type { DownloadTaskRead } from '../types';
import AddDownloadDialog from './AddDownloadDialog';

const STATUS_LABEL: Record<string, string> = {
  pending: '等待中',
  queued: '已入队',
  downloading: '下载中',
  merging: '合并中',
  ready: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

function formatPercent(progress: number): string {
  const n = Math.max(0, Math.min(100, progress));
  return `${n.toFixed(1)}%`;
}

interface TaskRowProps {
  task: DownloadTaskRead;
  onCancel: (id: number) => void;
  onRetry: (id: number) => void;
  onDelete: (id: number) => void;
}

function TaskRow({ task, onCancel, onRetry, onDelete }: TaskRowProps) {
  const [live, setLive] = useState<DownloadTaskRead>(task);

  const onProgressPush = useCallback((updated: DownloadTaskRead) => {
    setLive(updated);
  }, []);

  const sseUrl =
    live.status === 'downloading' ||
    live.status === 'merging' ||
    live.status === 'queued' ||
    live.status === 'pending'
      ? `/api/downloads/${task.id}/stream`
      : null;
  useSSE<DownloadTaskRead>(sseUrl, onProgressPush);

  useEffect(() => {
    setLive(task);
  }, [task]);

  const showProgress = live.status === 'downloading' || live.status === 'merging';
  const showCancel =
    live.status === 'downloading' ||
    live.status === 'merging' ||
    live.status === 'queued' ||
    live.status === 'pending';
  const showRetry = live.status === 'failed' || live.status === 'cancelled';
  const showDelete =
    live.status === 'ready' || live.status === 'failed' || live.status === 'cancelled';

  return (
    <li className={`download-row download-row--${live.status}`}>
      <div className="download-row__title-cell">
        <span className="download-row__title" title={live.title || live.url}>
          {live.title || live.url}
        </span>
      </div>

      <div className="download-row__link-cell">
        <a
          href={live.url}
          target="_blank"
          rel="noopener noreferrer"
          className="download-row__link"
          title="在 YouTube 上查看原始视频"
        >
          🔗 原始链接
        </a>
        {live.video_format_id && live.audio_format_id && (
          <span className="download-row__format-badge">
            V:{live.video_format_id} / A:{live.audio_format_id}
          </span>
        )}
      </div>

      <div className="download-row__progress-cell">
        {showProgress ? (
          <div className="download-row__progress">
            <div className="download-row__progress-track">
              <div
                className="download-row__progress-fill"
                style={{ width: `${Math.max(0, Math.min(100, live.progress))}%` }}
              />
            </div>
            <span className="download-row__progress-percent">
              {formatPercent(live.progress)}
            </span>
            <span className="download-row__progress-speed">
              {live.speed || ''} {live.eta ? `· 剩余 ${live.eta}` : ''}
            </span>
          </div>
        ) : live.status === 'queued' && live.retry_count > 0 ? (
          <span className="download-row__retry-hint">
            ⏳ 自动重试中 ({live.retry_count}/{live.max_retries})
          </span>
        ) : (
          <span className="download-row__progress-empty">—</span>
        )}
      </div>

      <div className="download-row__status-cell">
        <span className={`download-badge download-badge--${live.status}`}>
          {STATUS_LABEL[live.status] || live.status}
        </span>
      </div>

      <div className="download-row__actions-cell">
        {showRetry && (
          <button
            type="button"
            className="icon-btn icon-btn--primary"
            onClick={() => onRetry(live.id)}
            title="重试此任务"
            aria-label="重试"
          >
            🔄
          </button>
        )}
        {showCancel && (
          <button
            type="button"
            className="icon-btn icon-btn--danger"
            onClick={() => onCancel(live.id)}
            title="取消此任务"
            aria-label="取消"
          >
            ❌
          </button>
        )}
        {showDelete && (
          <button
            type="button"
            className="icon-btn icon-btn--danger"
            onClick={() => onDelete(live.id)}
            title="从历史中删除此任务"
            aria-label="删除"
          >
            🗑
          </button>
        )}
      </div>
    </li>
  );
}

export function DownloadTasks() {
  const { data, loading, error, reload } = useApi<DownloadTaskRead[]>(
    '/api/downloads',
  );
  const [addOpen, setAddOpen] = useState(false);

  const handleCancel = async (id: number) => {
    try {
      await fetch(`/api/downloads/${id}`, { method: 'DELETE' });
    } catch {
      // 忽略，仍刷新
    }
    reload();
  };

  const handleRetry = async (id: number) => {
    try {
      await fetch(`/api/downloads/${id}/retry`, { method: 'POST' });
    } catch {
      // 忽略，仍刷新
    }
    reload();
  };

  const handleDelete = async (id: number) => {
    try {
      await fetch(`/api/downloads/${id}`, { method: 'DELETE' });
    } catch {
      // 忽略，仍刷新
    }
    reload();
  };

  return (
    <div className="downloads">
      <header className="downloads__header">
        <div className="downloads__title-area">
          <h1>下载任务</h1>
          <p className="downloads__subtitle">单行展示：标题 / 链接 / 进度 / 状态 / 操作</p>
        </div>
        <div className="downloads__actions">
          <button type="button" className="btn btn--ghost" onClick={reload}>
            🔄 刷新
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => setAddOpen(true)}
          >
            <span>＋</span> 新增下载
          </button>
        </div>
      </header>

      {loading && <div className="downloads__status">加载中…</div>}
      {error && (
        <div className="downloads__status downloads__status--error">
          任务列表加载失败：{error.message}
        </div>
      )}
      {!loading && !error && (!data || data.length === 0) && (
        <div className="downloads__empty">
          <p className="downloads__empty-icon">📥</p>
          <h3>暂无下载任务</h3>
          <p>点击右上角的「新增下载」开始您的第一个 YouTube 视频离线备灾。</p>
        </div>
      )}

      {data && data.length > 0 && (
        <ul className="downloads__list">
          {data.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              onCancel={handleCancel}
              onRetry={handleRetry}
              onDelete={handleDelete}
            />
          ))}
        </ul>
      )}

      <AddDownloadDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={reload}
      />
    </div>
  );
}

export default DownloadTasks;