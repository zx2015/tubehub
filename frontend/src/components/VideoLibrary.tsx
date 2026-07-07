/**
 * VideoLibrary — 视频库首页
 *
 * 设计依据：docs/design/04-frontend-components.md §4.4
 *
 * 功能：
 *  - 响应式网格（手机 2 / 平板 3 / 桌面 5 列，由 CSS 媒体查询控制）
 *  - 顶部工具栏：搜索框、排序、新增下载
 *  - 选中 ≥1 项时浮现批量操作栏
 *  - 单删 / 批量删使用 ConfirmDialog 兜底
 *  - API 失败时降级为空状态
 */
import { useMemo, useState } from 'react';
import { useApi } from '../hooks/useApi';
import type { VideoRead } from '../types';
import VideoCard from './VideoCard';
import AddDownloadDialog from './AddDownloadDialog';
import ConfirmDialog from './ConfirmDialog';

type SortKey = 'created_desc' | 'created_asc' | 'title_asc' | 'title_desc';

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'created_desc', label: '最新添加' },
  { value: 'created_asc', label: '最早添加' },
  { value: 'title_asc', label: '标题 A→Z' },
  { value: 'title_desc', label: '标题 Z→A' },
];

export function VideoLibrary() {
  const { data, loading, error, reload } = useApi<VideoRead[]>('/api/videos');
  const [keyword, setKeyword] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('created_desc');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [addOpen, setAddOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false);

  const filtered = useMemo(() => {
    if (!data) return [];
    const kw = keyword.trim().toLowerCase();
    const list = kw
      ? data.filter(
          (v) =>
            v.title.toLowerCase().includes(kw) ||
            (v.uploader?.toLowerCase().includes(kw) ?? false),
        )
      : data;
    const sorted = [...list];
    sorted.sort((a, b) => {
      switch (sortKey) {
        case 'created_asc':
          return a.created_at.localeCompare(b.created_at);
        case 'title_asc':
          return a.title.localeCompare(b.title);
        case 'title_desc':
          return b.title.localeCompare(a.title);
        case 'created_desc':
        default:
          return b.created_at.localeCompare(a.created_at);
      }
    });
    return sorted;
  }, [data, keyword, sortKey]);

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSingleDelete = async () => {
    if (pendingDelete == null) return;
    const id = pendingDelete;
    try {
      await fetch(`/api/videos/${id}`, { method: 'DELETE' });
    } catch {
      // 忽略网络错误，仍尝试刷新
    }
    setPendingDelete(null);
    setSelected((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    reload();
  };

  const handleBatchDelete = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    try {
      await fetch('/api/videos/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids }),
      });
    } catch {
      // 忽略，仍尝试刷新
    }
    setSelected(new Set());
    setBatchDeleteOpen(false);
    reload();
  };

  const clearSelection = () => setSelected(new Set());

  const hasData = filtered.length > 0;
  const showEmpty = !loading && !error && (!data || data.length === 0);

  return (
    <div className="video-library">
      <header className="video-library__toolbar">
        <div className="video-library__search">
          <input
            type="search"
            placeholder="搜索标题或作者…"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            aria-label="搜索视频"
          />
        </div>
        <select
          className="video-library__sort"
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          aria-label="排序方式"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => setAddOpen(true)}
        >
          + 新增下载
        </button>
      </header>

      {selected.size > 0 && (
        <div className="video-library__batch-bar">
          <span className="video-library__batch-count">
            已选中 {selected.size} 项
          </span>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={clearSelection}
          >
            取消选择
          </button>
          <button
            type="button"
            className="btn btn--danger"
            onClick={() => setBatchDeleteOpen(true)}
          >
            批量删除
          </button>
        </div>
      )}

      {loading && <div className="video-library__status">加载中…</div>}
      {error && (
        <div className="video-library__status video-library__status--error">
          视频库加载失败：{error.message}
        </div>
      )}
      {showEmpty && (
        <div className="video-library__empty">
          <p>📭 视频库空空如也</p>
          <p>点击右上角「新增下载」开始你的第一个收藏。</p>
        </div>
      )}

      {hasData && (
        <div className="video-grid">
          {filtered.map((video) => (
            <VideoCard
              key={video.id}
              video={video}
              selected={selected.has(video.id)}
              onSelect={toggleSelect}
              onDelete={(id) => setPendingDelete(id)}
            />
          ))}
        </div>
      )}

      <AddDownloadDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={reload}
      />

      <ConfirmDialog
        open={pendingDelete != null}
        title="删除视频"
        message="确定删除该视频？该操作将同时清除历史记录，且不可恢复。"
        confirmText="删除"
        danger
        onConfirm={handleSingleDelete}
        onCancel={() => setPendingDelete(null)}
      />

      <ConfirmDialog
        open={batchDeleteOpen}
        title={`批量删除 ${selected.size} 个视频`}
        message="确认批量删除所选视频？所有相关历史记录将被清除，且不可恢复。"
        confirmText="批量删除"
        danger
        onConfirm={handleBatchDelete}
        onCancel={() => setBatchDeleteOpen(false)}
      />
    </div>
  );
}

export default VideoLibrary;