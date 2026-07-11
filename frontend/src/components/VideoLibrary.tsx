/**
 * VideoLibrary — 视频库首页（仿 YouTube 极致美学重构）
 *
 * 设计依据：docs/design/04-frontend-components.md §4.4
 *
 * 功能：
 *  - 顶部工具栏：[+ 新增下载] 按钮 + 搜索框 + 排序下拉
 *  - 顶部 Hero 区：统计概览（总视频、未观看、已观看、已看完）+ 全局搜索
 *  - 横向 Chips 筛选条：全部 / 未观看 / 已观看 / 已看完 / 最近添加
 *  - 响应式网格（手机 2 / 平板 3 / 桌面 5 列）
 *  - 选中 ≥1 项时浮现批量操作栏
 *  - 单删 / 批量删使用 ConfirmDialog 兜底
 *  - API 失败时降级为空状态
 */
import { useEffect, useMemo, useState } from 'react';
import { useApi } from '../hooks/useApi';
import type { VideoRead } from '../types';
import VideoCard from './VideoCard';
import ConfirmDialog from './ConfirmDialog';

type SortKey = 'created_desc' | 'created_asc' | 'title_asc' | 'title_desc';
type WatchFilter = 'all' | 'unwatched' | 'watching' | 'completed';

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'created_desc', label: '最新添加' },
  { value: 'created_asc', label: '最早添加' },
  { value: 'title_asc', label: '标题 A→Z' },
  { value: 'title_desc', label: '标题 Z→A' },
];

const CHIP_OPTIONS: { value: WatchFilter; label: string; icon: string }[] = [
  { value: 'all', label: '全部', icon: '📺' },
  { value: 'unwatched', label: '未观看', icon: '🆕' },
  { value: 'watching', label: '已观看', icon: '⏳' },
  { value: 'completed', label: '已看完', icon: '✓' },
];

function getWatchStatus(v: VideoRead): WatchFilter {
  if (!v.last_position || v.last_position <= 0) return 'unwatched';
  const duration = v.duration ?? 0;
  if (duration > 0 && v.last_position >= duration * 0.95) return 'completed';
  if (v.last_position > 5) return 'watching';
  return 'unwatched';
}

export function VideoLibrary() {
  const { data, loading, error, reload } = useApi<VideoRead[]>('/api/videos');
  const [keyword, setKeyword] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('created_desc');
  const [watchFilter, setWatchFilter] = useState<WatchFilter>('all');

  // 每 30 秒自动刷新一次视频列表（下载完成后无需手动 F5）
  useEffect(() => {
    const timer = setInterval(() => { reload(); }, 30_000);
    return () => clearInterval(timer);
  }, [reload]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false);

  // 统计（依赖全集，与筛选无关）
  const stats = useMemo(() => {
    if (!data) return { total: 0, unwatched: 0, watching: 0, completed: 0 };
    let unwatched = 0, watching = 0, completed = 0;
    for (const v of data) {
      const s = getWatchStatus(v);
      if (s === 'unwatched') unwatched++;
      else if (s === 'watching') watching++;
      else if (s === 'completed') completed++;
    }
    return { total: data.length, unwatched, watching, completed };
  }, [data]);

  // 过滤 + 排序
  const filtered = useMemo(() => {
    if (!data) return [];
    const kw = keyword.trim().toLowerCase();
    const list = data.filter((v) => {
      if (kw) {
        const hitKw =
          v.title.toLowerCase().includes(kw) ||
          (v.uploader?.toLowerCase().includes(kw) ?? false);
        if (!hitKw) return false;
      }
      if (watchFilter !== 'all' && getWatchStatus(v) !== watchFilter) {
        return false;
      }
      return true;
    });

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
  }, [data, keyword, sortKey, watchFilter]);

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
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
  const showFilteredEmpty =
    !loading && !error && !!data && data.length > 0 && filtered.length === 0;

  return (
    <div className="video-library">
      {/* === 顶部工具栏 === */}
      <div className="video-library__toolbar">
        <div className="video-library__search">
          <span className="video-library__search-icon">🔍</span>
          <input
            type="search"
            placeholder="搜索标题或上传者…"
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
      </div>

      {/* === 统计概览（Stats Panel） === */}
      {data && data.length > 0 && (
        <div className="video-library__stats">
          <div className="stat-card stat-card--total">
            <div className="stat-card__value">{stats.total}</div>
            <div className="stat-card__label">视频总数</div>
          </div>
          <div className="stat-card stat-card--unwatched">
            <div className="stat-card__value">{stats.unwatched}</div>
            <div className="stat-card__label">🆕 未观看</div>
          </div>
          <div className="stat-card stat-card--watching">
            <div className="stat-card__value">{stats.watching}</div>
            <div className="stat-card__label">⏳ 已观看</div>
          </div>
          <div className="stat-card stat-card--completed">
            <div className="stat-card__value">{stats.completed}</div>
            <div className="stat-card__label">✓ 已看完</div>
          </div>
        </div>
      )}

      {/* === Chips 筛选条（YouTube 风格） === */}
      {data && data.length > 0 && (
        <div className="chips">
          {CHIP_OPTIONS.map((opt) => {
            const count =
              opt.value === 'all'
                ? stats.total
                : opt.value === 'unwatched'
                  ? stats.unwatched
                  : opt.value === 'watching'
                    ? stats.watching
                    : stats.completed;
            return (
              <button
                key={opt.value}
                type="button"
                className={`chip${watchFilter === opt.value ? ' chip--active' : ''}`}
                onClick={() => setWatchFilter(opt.value)}
              >
                <span className="chip__icon">{opt.icon}</span>
                <span>{opt.label}</span>
                <span className="chip__count">{count}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* === 批量操作栏 === */}
      {selected.size > 0 && (
        <div className="video-library__batch-bar">
          <span className="video-library__batch-count">
            已选 {selected.size} 项
          </span>
          <button type="button" className="btn btn--ghost" onClick={clearSelection}>
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
          <p className="video-library__empty-icon">📭</p>
          <h3>视频库空空如也</h3>
          <p>前往「下载任务」页面新建下载任务来开始您的第一个收藏。</p>
        </div>
      )}
      {showFilteredEmpty && (
        <div className="video-library__empty">
          <p className="video-library__empty-icon">🔍</p>
          <h3>没有匹配的视频</h3>
          <p>尝试更换关键字或切换筛选状态。</p>
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