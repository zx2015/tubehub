/**
 * AddDownloadDialog — 新增下载对话框
 *
 * 设计依据：docs/design/04-frontend-components.md §4.7
 *
 * 流程：
 *  1. 用户输入 URL + 选择画质
 *  2. POST /api/downloads/check 检测冲突
 *  3. 有冲突时回显，提示用户选择是否覆盖
 *  4. POST /api/downloads 提交任务
 *
 * 简化：后端 check/download 接口尚未完全实现时使用 mock 兜底，
 *      失败则展示错误但不影响关闭。
 */
import { useState } from 'react';

interface AddDownloadDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated?: () => void;
}

type Quality = 'best' | '1080p' | '720p' | '480p' | 'worst';

export function AddDownloadDialog({ open, onClose, onCreated }: AddDownloadDialogProps) {
  const [url, setUrl] = useState('');
  const [quality, setQuality] = useState<Quality>('best');
  const [overwrite, setOverwrite] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checkResult, setCheckResult] = useState<{
    conflict: boolean;
    title?: string;
  } | null>(null);

  if (!open) return null;

  const reset = () => {
    setUrl('');
    setQuality('best');
    setOverwrite(false);
    setSubmitting(false);
    setError(null);
    setCheckResult(null);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleCheck = async () => {
    if (!url.trim()) {
      setError('请输入有效的 URL');
      return;
    }
    setError(null);
    try {
      const resp = await fetch('/api/downloads/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      });
      if (!resp.ok) {
        // 后端尚未实现时降级为无冲突
        setCheckResult({ conflict: false });
        return;
      }
      const data = await resp.json();
      setCheckResult({
        conflict: Boolean(data?.conflict),
        title: data?.title ?? undefined,
      });
    } catch {
      // 网络错误兜底
      setCheckResult({ conflict: false });
    }
  };

  const handleSubmit = async () => {
    if (!url.trim()) {
      setError('请输入有效的 URL');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const resp = await fetch('/api/downloads', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: url.trim(),
          format_type: 'video',
          quality,
          overwrite,
          download_subtitles: false,
        }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        setError(`提交失败 (${resp.status}): ${text || '未知错误'}`);
        setSubmitting(false);
        return;
      }
      onCreated?.();
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败');
      setSubmitting(false);
    }
  };

  return (
    <div
      className="add-download__backdrop"
      role="dialog"
      aria-modal="true"
      onClick={handleClose}
    >
      <div className="add-download" onClick={(e) => e.stopPropagation()}>
        <h2 className="add-download__title">新增下载</h2>

        <label className="add-download__label">
          视频 URL
          <input
            type="url"
            className="add-download__input"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
          />
        </label>

        <div className="add-download__row">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={handleCheck}
            disabled={!url.trim() || submitting}
          >
            检测冲突
          </button>

          <label className="add-download__label add-download__label--inline">
            画质
            <select
              className="add-download__select"
              value={quality}
              onChange={(e) => setQuality(e.target.value as Quality)}
            >
              <option value="best">最佳</option>
              <option value="1080p">1080p</option>
              <option value="720p">720p</option>
              <option value="480p">480p</option>
              <option value="worst">最低</option>
            </select>
          </label>
        </div>

        {checkResult?.conflict && (
          <div className="add-download__conflict">
            <p>
              ⚠️ 该视频已在库中：<strong>{checkResult.title ?? '未知标题'}</strong>
            </p>
            <label className="add-download__checkbox">
              <input
                type="checkbox"
                checked={overwrite}
                onChange={(e) => setOverwrite(e.target.checked)}
              />
              覆盖现有下载
            </label>
          </div>
        )}

        {error && <div className="add-download__error">{error}</div>}

        <div className="add-download__actions">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={handleClose}
            disabled={submitting}
          >
            取消
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={handleSubmit}
            disabled={submitting || !url.trim()}
          >
            {submitting ? '提交中…' : '添加'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default AddDownloadDialog;