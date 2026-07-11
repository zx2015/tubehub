import { useState } from 'react';

interface FormatOption {
  id: number;
  label: string;
  ext?: string;
  height?: number;
  vcodec?: string;
  abr?: number;
  acodec?: string;
  filesize?: number | null;
}

/** 与后端 DownloadCheckResponse 字段对齐 */
interface CheckResponse {
  conflict: boolean;           // 是否已存在（后端字段名）
  existing_video?: { id: number; title: string } | null;
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
  /** 检查成功时锁定的 URL，提交时使用此值，避免输入框被清空导致空 URL */
  const [checkedUrl, setCheckedUrl] = useState('');
  const [checking, setChecking] = useState(false);
  const [creating, setCreating] = useState(false);
  const [checkResult, setCheckResult] = useState<CheckResponse | null>(null);
  const [videoFormatId, setVideoFormatId] = useState<number | ''>('');
  const [audioFormatId, setAudioFormatId] = useState<number | ''>('');
  const [overwrite, setOverwrite] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!open) return null;

  const handleCheck = async () => {
    const trimmed = url.trim();
    if (!trimmed) {
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
        body: JSON.stringify({ url: trimmed }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: CheckResponse = await res.json();
      setCheckResult(data);
      setCheckedUrl(trimmed); // 锁定 URL

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

      if (data.conflict) {
        setOverwrite(true);
      }
    } catch (e: any) {
      setErrorMsg(`解析失败: ${e?.message ?? e}`);
    } finally {
      setChecking(false);
    }
  };

  const handleSubmit = async () => {
    if (!checkResult || !checkedUrl) {
      setErrorMsg('请先点击"获取信息"');
      return;
    }
    if (!videoFormatId || !audioFormatId) {
      setErrorMsg('视频格式与音频格式都必须选择');
      return;
    }
    if (checkResult.conflict && !overwrite) {
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
          url: checkedUrl,   // 用锁定 URL，不用实时输入框
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
      // 后端返回 list，取第一条的 id
      const taskId = Array.isArray(data) ? (data[0]?.id ?? 0) : (data?.id ?? 0);
      onCreated?.(taskId);
      handleClose();
    } catch (e: any) {
      setErrorMsg(`提交失败: ${e?.message ?? e}`);
    } finally {
      setCreating(false);
    }
  };

  const handleClose = () => {
    setUrl('');
    setCheckedUrl('');
    setCheckResult(null);
    setVideoFormatId('');
    setAudioFormatId('');
    setOverwrite(false);
    setErrorMsg(null);
    onClose();
  };

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
          <button type="button" className="add-download__close" onClick={handleClose} aria-label="关闭">
            ✕
          </button>
        </header>

        <div className="add-download__body">
          {/* URL 输入 */}
          <div className="add-download__row add-download__row--url">
            <label className="add-download__label">YouTube 链接</label>
            <div className="add-download__url-group">
              <input
                className="add-download__input"
                type="text"
                placeholder="https://www.youtube.com/watch?v=..."
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value);
                  // URL 变化时清除上次检查结果，要求重新获取
                  if (checkResult) {
                    setCheckResult(null);
                    setCheckedUrl('');
                  }
                }}
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

          {/* 检查结果 */}
          {checkResult && (
            <>
              {checkResult.conflict && checkResult.existing_video && (
                <div className="add-download__notice add-download__notice--warn">
                  ⚠️ 该视频已在库中: <strong>{checkResult.existing_video.title}</strong>
                </div>
              )}

              {checkResult.title && (
                <div className="add-download__row">
                  <label className="add-download__label">标题</label>
                  <div className="add-download__readonly">{checkResult.title}</div>
                </div>
              )}

              {checkResult.video_formats && checkResult.video_formats.length > 0 && (
                <div className="add-download__row">
                  <label className="add-download__label">视频格式</label>
                  <select
                    className="add-download__select"
                    value={videoFormatId}
                    onChange={(e) => setVideoFormatId(Number(e.target.value))}
                  >
                    {checkResult.video_formats.map((f) => (
                      <option key={f.id} value={f.id}>{f.label}</option>
                    ))}
                  </select>
                </div>
              )}

              {checkResult.audio_formats && checkResult.audio_formats.length > 0 && (
                <div className="add-download__row">
                  <label className="add-download__label">音频格式</label>
                  <select
                    className="add-download__select"
                    value={audioFormatId}
                    onChange={(e) => setAudioFormatId(Number(e.target.value))}
                  >
                    {checkResult.audio_formats.map((f) => (
                      <option key={f.id} value={f.id}>{f.label}</option>
                    ))}
                  </select>
                </div>
              )}

              {checkResult.conflict && (
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
          <button type="button" className="add-download__btn" onClick={handleClose} disabled={creating}>
            取消
          </button>
          <button
            type="button"
            className="add-download__btn add-download__btn--success"
            onClick={handleSubmit}
            disabled={
              creating ||
              !checkResult ||
              !checkedUrl ||
              !videoFormatId ||
              !audioFormatId ||
              (checkResult.conflict && !overwrite)
            }
          >
            {creating ? '🚀 任务创建中...' : '开始下载'}
          </button>
        </footer>
      </div>
    </div>
  );
}
