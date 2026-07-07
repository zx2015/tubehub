/**
 * DownloadTasks — 下载任务列表
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
 */
import { useCallback, useEffect, useState } from 'react';
import { useApi } from '../hooks/useApi';
import { useSSE } from '../hooks/useSSE';
import type { DownloadTaskRead } from '../types';

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
  // 对每个处于进行中状态的任务建立 SSE 订阅
  const isActive = ['pending', 'queued', 'downloading', 'merging'].includes(
    task.status,
  );
  const [live, setLive] = useState<DownloadTaskRead>(task);

  // 当 task prop 变化时同步初始值
  useEffect(() => {
    setLive(task);
  }, [task]);

  const handleMessage = useCallback((data: DownloadTaskRead) => {
    setLive(data);
  }, []);

  useSSE<DownloadTaskRead>(
    isActive ? `/api/downloads/${task.id}/stream` : null,
    handleMessage,
  );

  const status = live.status;
  const canCancel = !['ready', 'cancelled', 'failed'].includes(status);
  const canRetry = status === 'failed' && live.retry_count < live.max_retries;

  return (
    <li className={`download-row download-row--${status}`}>
      <div className="download-row__main">
        <div className="download-row__title">
          {live.title ?? live.url}
        </div>
        <div className="download-row__meta">
          <span className={`download-row__status download-row__status--${status}`}>
            {STATUS_LABEL[status] ?? status}
          </span>
          <span className="download-row__quality">{live.quality}</span>
          {live.speed && <span>{live.speed}</span>}
          {live.eta && <span>ETA {live.eta}</span>}
        </div>
        <ProgressBar value={live.progress} />
        <div className="download-row__progress-label">
          {formatPercent(live.progress)}
          {live.retry_count > 0 && (
            <span className="download-row__retry">
              · 已重试 {live.retry_count}/{live.max_retries}
            </span>
          )}
        </div>
        {live.error_message && (
          <div className="download-row__error">{live.error_message}</div>
        )}
      </div>
      <div className="download-row__actions">
        {canRetry && (
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => onRetry(live.id)}
          >
            重试
          </button>
        )}
        {canCancel && (
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
        <h1>下载任务</h1>
        <button
          type="button"
          className="btn btn--ghost"
          onClick={reload}
        >
          刷新
        </button>
      </header>

      {loading && <div className="downloads__status">加载中…</div>}
      {error && (
        <div className="downloads__status downloads__status--error">
          任务列表加载失败：{error.message}
        </div>
      )}
      {!loading && !error && (!data || data.length === 0) && (
        <div className="downloads__empty">
          <p>📭 暂无下载任务</p>
          <p>前往「视频库」点击「新增下载」开始。</p>
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
    </div>
  );
}

export default DownloadTasks;