/**
 * AddDownloadPanel — 页面内快速悬浮下载面板 (Gmail / 写信浮窗风格)
 *
 * 关键设计：
 *  - 挂载在 Layout 级别，全站常驻在右下角
 *  - 无遮罩 Backdrop：用户在下载时可以继续自由点击、浏览主页面，体验极为流畅
 *  - 最小化 (Minimize)：点击 "➖" 可折叠收缩为右下角小胶囊，不占空间；再次点击展开
 *  - 异步进行：提交后，面板内部显示 Progress Spinner 与 "Scraper 解析中..."，用户可以在主页面看到成果
 */
import { useState } from 'react';

interface AddDownloadPanelProps {
  onCreated?: () => void;
}

type Quality = 'best' | '1080p' | '720p' | '480p' | 'worst';

export function AddDownloadPanel({ onCreated }: AddDownloadPanelProps) {
  const [isOpen, setIsOpen] = useState(false);                  // 是否打开面板
  const [isMinimized, setIsMinimized] = useState(false);          // 是否最小化
  const [url, setUrl] = useState('');
  const [quality, setQuality] = useState<Quality>('best');
  const [overwrite, setOverwrite] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checkResult, setCheckResult] = useState<{
    conflict: boolean;
    title?: string;
  } | null>(null);

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
    setIsOpen(false);
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
      // 成功提交后，自动最小化提示用户 (类似浏览器下载下载气泡)，并在 3 秒后关闭
      setIsMinimized(true);
      setTimeout(() => {
        handleClose();
      }, 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败');
      setSubmitting(false);
    }
  };

  // 1. 面板未开启状态：显示悬浮触发气泡 (Minimized Button)
  if (!isOpen) {
    return (
      <button
        type="button"
        className="floating-trigger"
        onClick={() => setIsOpen(true)}
        title="快速添加下载任务"
      >
        <span className="floating-trigger__icon">📥</span>
        <span className="floating-trigger__text">快速下载</span>
      </button>
    );
  }

  // 2. 最小化折叠态
  if (isMinimized) {
    return (
      <div className="floating-panel floating-panel--minimized">
        <div className="floating-panel__header" onClick={() => setIsMinimized(false)}>
          <span className="floating-panel__title-icon">📥</span>
          <span className="floating-panel__minimized-title">
            {submitting ? '🚀 Scraper 元数据提取中...' : '📥 快速下载面板已折叠'}
          </span>
          <div className="floating-panel__controls">
            <button type="button" onClick={() => setIsMinimized(false)} title="展开">➕</button>
            <button type="button" onClick={handleClose} title="关闭">❌</button>
          </div>
        </div>
      </div>
    );
  }

  // 3. 展开后的完整写信窗态
  return (
    <div className="floating-panel">
      <div className="floating-panel__header">
        <div className="floating-panel__brand">
          <span className="floating-panel__title-icon">📥</span>
          <span className="floating-panel__title-text">快速新建下载</span>
        </div>
        <div className="floating-panel__controls">
          <button type="button" onClick={() => setIsMinimized(true)} title="最小化">➖</button>
          <button type="button" onClick={handleClose} title="关闭">❌</button>
        </div>
      </div>

      <div className="floating-panel__body">
        <div className="floating-panel__field">
          <label>YouTube 视频 / 歌单 URL</label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="粘贴 watch?v= 或 playlist?list="
            disabled={submitting}
          />
        </div>

        <div className="floating-panel__row">
          <div className="floating-panel__field">
            <label>格式</label>
            <input type="text" value="视频 (.mp4)" disabled />
          </div>

          <div className="floating-panel__field">
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

        <div style={{ marginTop: '8px' }}>
          <button
            type="button"
            className="btn btn--ghost"
            style={{ width: '100%', height: '32px', fontSize: '12px' }}
            onClick={handleCheck}
            disabled={!url.trim() || submitting}
          >
            🔍 检测冲突（防重）
          </button>
        </div>

        {checkResult && (
          <div className="floating-panel__conflict">
            {checkResult.conflict ? (
              <>
                <p>⚠️ 该视频已在库中：</p>
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
              <p className="conflict-ok">✅ 此视频未下载过，可以安全添加</p>
            )}
          </div>
        )}

        {error && <div className="floating-panel__error">⚠️ {error}</div>}
      </div>

      <div className="floating-panel__footer">
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
          {submitting ? '🚀 提交并解析中…' : '开始下载'}
        </button>
      </div>
    </div>
  );
}

export default AddDownloadPanel;