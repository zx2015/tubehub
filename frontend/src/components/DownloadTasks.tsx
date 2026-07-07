/**
 * DownloadTasks — 下载任务列表（仿 YouTube 体验重构：内置新建下载）
 *
 * 设计依据：docs/design/04-frontend-components.md §4.2
 *
 * 功能：
 *  - 列出所有下载任务（GET /api/downloads）
 *  - 每个任务通过 SSE（GET /api/downloads/{id}/stream）实时更新进度
 *  - 状态标签：Pending / Queued / Downloading / Merging / Ready / Failed / Cancelled
 *  - 进度条：百分比 + 速度 + ETA
 *  - Failed 任务支持「重试」（POST /api/downloads/{id}/retry）
 *  - 任务支持「取消/删除」（DELETE /api/downloads/{id}）
 *  - **新增下载入口重置于此（用户 2026-07-07 决策）**
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

function ProgressBar({ value }: { value: number }) {
  const n = Math.max(0, Math.min(100, value));
  return (
    <div className="download-row__progress-track" role="progressbar" aria-valuenow={n}>
      <div
        className="download-row__progress-fill"
        style={{ width: `${n}%` }}
      />
    </div>
  );
}

interface TaskRowProps {
  task: DownloadTaskRead;
  onCancel: (id: number) => void;
  onRetry: (id: number) => void;
}

function TaskRow({ task, onCancel, onRetry }: TaskRowProps) {
  const [live, setLive] = useState<DownloadTaskRead>(task);

  // 当服务端数据库变更时，利用 SSE 推送最新进度给组件
  const onProgressPush = useCallback((updated: DownloadTaskRead) => {
    setLive(updated);
  }, []);

  // 仅在任务处于进行中状态时，开启 SSE 进度同步
  const sseUrl =
    live.status === 'downloading' || live.status === 'merging' || live.status === 'queued'
      ? `/api/downloads/${task.id}/stream`
      : null;

  useSSE<DownloadTaskRead>(sseUrl || '', onProgressPush);

  // 兜底同步 initial props 变更
  useEffect(() => {
    setLive(task);
  }, [task]);

  const showPercent = live.status === 'downloading' || live.status === 'merging';
  const showProgress = live.status === 'downloading' || live.status === 'merging';
  const showCancel =
    live.status === 'pending' ||
    live.status === 'queued' ||
    live.status === 'downloading' ||
    live.status === 'merging';
  const showRetry = live.status === 'failed';

  return (
    <li className={`download-row download-row--${live.status}`}>
      <div className="download-row__info">
        <span className="download-row__title" title={live.title || live.url}>
          {live.title || live.url}
        </span>
        <div className="download-row__meta">
          <span className={`download-badge download-badge--${live.status}`}>
            {STATUS_LABEL[live.status] || live.status}
          </span>
          {live.status === 'downloading' && (
            <>
              <span className="download-row__stat">{live.speed || '0 B/s'}</span>
              <span className="download-row__divider">•</span>
              <span className="download-row__stat">剩余 {live.eta || '00:00'}</span>
            </>
          )}
          {live.retry_count > 0 && live.status === 'queued' && (
            <span className="download-row__retry-hint">
              (正在自动重试 {live.retry_count}/{live.max_retries}...)
            </span>
          )}
        </div>
      </div>

      <div className="download-row__control">
        {showPercent && (
          <span className="download-row__percent">
            {formatPercent(live.progress)}
          </span>
        )}

        {showProgress && <ProgressBar value={live.progress} />}

        {showRetry && (
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => onRetry(live.id)}
          >
            重试
          </button>
        )}

        {showCancel && (
          <button
            type="button"
            className="btn btn--danger"
            onClick={() => onCancel(live.id)}
          >
            取消
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

  return (
    <div className="downloads">
      <header className="downloads__header">
        <div className="downloads__title-area">
          <h1>下载任务</h1>
          <p className="downloads__subtitle">在这里管理与新建您的 YouTube 视频下载流水线</p>
        </div>
        <div className="downloads__actions">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={reload}
          >
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