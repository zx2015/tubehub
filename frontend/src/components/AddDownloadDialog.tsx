/**
 * AddDownloadDialog — 新增下载对话窗口（经典居中遮罩美学）
 *
 * 设计依据：docs/design/04-frontend-components.md §4.7
 *
 * 重构（2026-07-08）：
 *  - 100% 独立于页面主流，以绝对定位（position: fixed）与高 z-index 浮动在页面最上方。
 *  - 配备半透明黑色遮罩（rgba(0, 0, 0, 0.6)），阻断焦点，使用户视线完全聚焦于新增表单。
 */
import { useState, useEffect } from 'react';

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

  // 每次打开弹窗时，状态复位
  useEffect(() => {
    if (open) {
      setUrl('');
      setQuality('best');
      setOverwrite(false);
      setSubmitting(false);
      setError(null);
      setCheckResult(null);
    }
  }, [open]);

  if (!open) return null;

  const handleClose = () => {
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
        setCheckResult({ conflict: false });
        return;
      }
      const data = await resp.json();
      setCheckResult({
        conflict: Boolean(data?.conflict),
        title: data?.title ?? undefined,
      });
    } catch {
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
        }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        setError(`提交失败: ${text || '未知错误'}`);
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
      className="add-download-backdrop"
      role="dialog"
      aria-modal="true"
      onClick={handleClose}
    >
      <div className="add-download-window" onClick={(e) => e.stopPropagation()}>
        <div className="add-download-window__header">
          <h2 className="add-download-window__title">📺 新建下载任务</h2>
          <button type="button" className="add-download-window__close" onClick={handleClose} title="关闭">
            ❌
          </button>
        </div>

        <div className="add-download-window__body">
          <div className="add-download-window__field">
            <label>YouTube 视频 / 歌单 URL</label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
              disabled={submitting}
            />
          </div>

          <div className="add-download-window__row">
            <div className="add-download-window__field">
              <label>格式</label>
              <input type="text" value="视频 (.mp4)" disabled />
            </div>

            <div className="add-download-window__field">
              <label>画质</label>
              <select
                value={quality}
                onChange={(e) => setQuality(e.target.value as Quality)}
                disabled={submitting}
              >
                <option value="best">最佳</option>
                <option value="1080p">1080p</option>
                <option value="720p">720p</option>
                <option value="480p">480p</option>
                <option value="worst">最低</option>
              </select>
            </div>
          </div>

          <div style={{ marginTop: '4px' }}>
            <button
              type="button"
              className="btn btn--ghost"
              style={{ width: '100%', height: '32px', fontSize: '12px' }}
              onClick={handleCheck}
              disabled={!url.trim() || submitting}
            >
              🔍 检测冲突 (防重下载)
            </button>
          </div>

          {checkResult && (
            <div className="add-download-window__conflict">
              {checkResult.conflict ? (
                <>
                  <p>⚠️ 视频已在库中：</p>
                  <p className="conflict-title"><strong>{checkResult.title ?? '未知标题'}</strong></p>
                  <label className="conflict-checkbox">
                    <input
                      type="checkbox"
                      checked={overwrite}
                      onChange={(e) => setOverwrite(e.target.checked)}
                    />
                    覆盖现有文件
                  </label>
                </>
              ) : (
                <p className="conflict-ok">✅ 此视频未在库中，可以安全下载</p>
              )}
            </div>
          )}

          {error && <div className="add-download-window__error">⚠️ {error}</div>}
        </div>

        <div className="add-download-window__footer">
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
            {submitting ? '🚀 提交中…' : '添加'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default AddDownloadDialog;