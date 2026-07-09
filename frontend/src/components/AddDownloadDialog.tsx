import { useState } from 'react';

interface FormatOption {
  id: number;
  label: string;
  // 可选的扩展字段
  ext?: string;
  height?: number;
  vcodec?: string;
  abr?: number;
  acodec?: string;
  filesize?: number | null;
}

interface CheckResponse {
  exists: boolean;
  existing_video?: {
    id: number;
    title: string;
  } | null;
  youtube_id?: string | null;
  title?: string | null;
  thumbnail?: string | null;
  video_formats?: FormatOption[];
  audio_formats?: FormatOption[];
}

interface AddDownloadDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated?: (taskId: number) => void;
}

export default function AddDownloadDialog({ open, onClose, onCreated }: AddDownloadDialogProps) {
  const [url, setUrl] = useState('');
  const [checking, setChecking] = useState(false);
  const [creating, setCreating] = useState(false);
  const [checkResult, setCheckResult] = useState<CheckResponse | null>(null);
  const [videoFormatId, setVideoFormatId] = useState<number | ''>('');
  const [audioFormatId, setAudioFormatId] = useState<number | ''>('');
  const [overwrite, setOverwrite] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!open) return null;

  const handleCheck = async () => {
    if (!url.trim()) {
      setErrorMsg('请先粘贴 YouTube 视频链接');
      return;
    }
    setChecking(true);
    setErrorMsg(null);
    setCheckResult(null);
    try {
      const res = await fetch('/api/downloads/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: CheckResponse = await res.json();
      setCheckResult(data);

      // 默认选中第一个
      if (data.video_formats && data.video_formats.length > 0) {
        setVideoFormatId(data.video_formats[0].id);
      } else {
        setVideoFormatId('');
      }
      if (data.audio_formats && data.audio_formats.length > 0) {
        setAudioFormatId(data.audio_formats[0].id);
      } else {
        setAudioFormatId('');
      }

      // 如果已存在，自动勾选覆盖
      if (data.exists) {
        setOverwrite(true);
      }
    } catch (e: any) {
      setErrorMsg(`解析失败: ${e?.message ?? e}`);
    } finally {
      setChecking(false);
    }
  };

  const handleSubmit = async () => {
    if (!checkResult) {
      setErrorMsg('请先点击"获取信息"');
      return;
    }
    if (!videoFormatId || !audioFormatId) {
      setErrorMsg('视频格式与音频格式都必须选择');
      return;
    }
    if (checkResult.exists && !overwrite) {
      setErrorMsg('该视频已下载，请勾选"覆盖已存在"后重试');
      return;
    }
    setCreating(true);
    setErrorMsg(null);
    try {
      const res = await fetch('/api/downloads', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: url.trim(),
          video_format_id: Number(videoFormatId),
          audio_format_id: Number(audioFormatId),
          overwrite,
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data = await res.json();
      onCreated?.(data.id ?? 0);
      handleClose();
    } catch (e: any) {
      setErrorMsg(`提交失败: ${e?.message ?? e}`);
    } finally {
      setCreating(false);
    }
  };

  const handleClose = () => {
    setUrl('');
    setCheckResult(null);
    setVideoFormatId('');
    setAudioFormatId('');
    setOverwrite(false);
    setErrorMsg(null);
    onClose();
  };

  // (formatBytes removed: each format's label is precomputed on backend)

  return (
    <div
      className="add-download__backdrop"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) handleClose();
      }}
    >
      <div className="add-download__modal" onClick={(e) => e.stopPropagation()}>
        <header className="add-download__header">
          <h2 className="add-download__title">新增下载</h2>
          <button
            type="button"
            className="add-download__close"
            onClick={handleClose}
            aria-label="关闭"
          >
            ✕
          </button>
        </header>

        <div className="add-download__body">
          {/* URL + 获取信息 按钮 */}
          <div className="add-download__row add-download__row--url">
            <label className="add-download__label">YouTube 链接</label>
            <div className="add-download__url-group">
              <input
                className="add-download__input"
                type="text"
                placeholder="https://www.youtube.com/watch?v=..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !checking) handleCheck();
                }}
              />
              <button
                type="button"
                className="add-download__btn add-download__btn--primary"
                onClick={handleCheck}
                disabled={checking || !url.trim()}
              >
                {checking ? '解析中...' : '获取信息'}
              </button>
            </div>
          </div>

          {/* 解析结果区域 */}
          {checkResult && (
            <>
              {checkResult.exists && checkResult.existing_video && (
                <div className="add-download__notice add-download__notice--warn">
                  ⚠️ 该视频已在库中: <strong>{checkResult.existing_video.title}</strong>
                </div>
              )}

              {/* Title 一行 */}
              {checkResult.title && (
                <div className="add-download__row">
                  <label className="add-download__label">标题</label>
                  <div className="add-download__readonly">{checkResult.title}</div>
                </div>
              )}

              {/* 视频格式一行 */}
              {checkResult.video_formats && checkResult.video_formats.length > 0 && (
                <div className="add-download__row">
                  <label className="add-download__label">视频格式</label>
                  <select
                    className="add-download__select"
                    value={videoFormatId}
                    onChange={(e) => setVideoFormatId(Number(e.target.value))}
                  >
                    {checkResult.video_formats.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* 音频格式一行 */}
              {checkResult.audio_formats && checkResult.audio_formats.length > 0 && (
                <div className="add-download__row">
                  <label className="add-download__label">音频格式</label>
                  <select
                    className="add-download__select"
                    value={audioFormatId}
                    onChange={(e) => setAudioFormatId(Number(e.target.value))}
                  >
                    {checkResult.audio_formats.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* 覆盖选项（仅在已存在时显示） */}
              {checkResult.exists && (
                <div className="add-download__row add-download__row--checkbox">
                  <label className="add-download__checkbox">
                    <input
                      type="checkbox"
                      checked={overwrite}
                      onChange={(e) => setOverwrite(e.target.checked)}
                    />
                    <span>覆盖已存在的视频</span>
                  </label>
                </div>
              )}
            </>
          )}

          {errorMsg && <div className="add-download__error">{errorMsg}</div>}
        </div>

        <footer className="add-download__footer">
          <button
            type="button"
            className="add-download__btn"
            onClick={handleClose}
            disabled={creating}
          >
            取消
          </button>
          <button
            type="button"
            className="add-download__btn add-download__btn--success"
            onClick={handleSubmit}
            disabled={
              creating ||
              !checkResult ||
              !videoFormatId ||
              !audioFormatId ||
              (checkResult.exists && !overwrite)
            }
          >
            {creating ? '🚀 任务创建中...' : '开始下载'}
          </button>
        </footer>
      </div>
    </div>
  );
}