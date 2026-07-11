/**
 * Settings — 全局设置页
 *
 * Cookie 管理：支持两种上传方式
 *   1. 选择本地 .txt 文件上传
 *   2. 直接粘贴文本内容
 */
import { useEffect, useRef, useState } from 'react';
import type { CookieStatus } from '../types';

export function Settings() {
  const [cookieText, setCookieText]     = useState('');
  const [cookieStatus, setCookieStatus] = useState<CookieStatus | null>(null);
  const [cookieMsg, setCookieMsg]       = useState<string | null>(null);
  const [uploading, setUploading]       = useState(false);
  const [dragOver, setDragOver]         = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch('/api/settings/cookies')
      .then(async (r) => (r.ok ? ((await r.json()) as CookieStatus) : null))
      .then((s) => { if (s) setCookieStatus(s); })
      .catch(() => undefined);
  }, []);

  // 核心：发送文本内容到后端
  const submitCookies = async (content: string) => {
    if (!content.trim()) {
      setCookieMsg('❌ Cookie 内容为空');
      return;
    }
    setUploading(true);
    setCookieMsg(null);
    try {
      const resp = await fetch('/api/settings/cookies', {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain' },
        body: content,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const status = (await resp.json()) as CookieStatus;
      setCookieStatus(status);
      setCookieText('');
      setCookieMsg(`✅ Cookie 已上传（${status.file_size ?? 0} 字节）`);
    } catch (err) {
      setCookieMsg(`❌ 上传失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setUploading(false);
    }
  };

  // 读取 File 对象并提交
  const handleFile = (file: File) => {
    if (!file.name.endsWith('.txt') && file.type !== 'text/plain') {
      setCookieMsg('❌ 请选择 .txt 格式的 Cookie 文件');
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      submitCookies(text);
    };
    reader.readAsText(file, 'utf-8');
  };

  // 文件选择框回调
  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    // 重置 input，允许重复选同一文件
    e.target.value = '';
  };

  // 拖拽上传
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const handleClearCookie = async () => {
    setCookieMsg(null);
    try {
      const resp = await fetch('/api/settings/cookies', { method: 'DELETE' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setCookieStatus({ has_cookie: false, updated_at: null, file_size: null, note: '' });
      setCookieMsg('✅ Cookie 已清除');
    } catch (err) {
      setCookieMsg(`❌ 清除失败：${err instanceof Error ? err.message : String(err)}`);
    }
  };

  return (
    <div className="settings">
      <h1 className="settings__title">设置</h1>

      {/* Cookie Section */}
      <section className="settings__section">
        <h2>Cookie 管理</h2>
        <p className="settings__hint">
          当下载受限视频（年龄限制、Bot 检测等）时，请上传浏览器导出的
          <strong> Netscape 格式</strong> Cookie 文件（通过浏览器扩展导出为 .txt）。
        </p>

        {/* 状态栏 */}
        <div className="settings__cookie-status">
          状态：
          {cookieStatus?.has_cookie ? (
            <strong className="settings__status--ok">
              ✅ 已配置（{cookieStatus.file_size ?? '?'} 字节）
              {cookieStatus.updated_at && (
                <span className="settings__status-time">
                  {' '}· 更新于 {new Date(cookieStatus.updated_at).toLocaleString('zh-CN')}
                </span>
              )}
            </strong>
          ) : (
            <strong className="settings__status--muted">⚠️ 未配置</strong>
          )}
        </div>

        {/* 文件拖拽区 */}
        <div
          className={`settings__drop-zone${dragOver ? ' settings__drop-zone--active' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <span className="settings__drop-icon">📂</span>
          <span className="settings__drop-text">
            点击选择 cookies.txt 文件，或拖拽文件到此处
          </span>
          <span className="settings__drop-hint">仅支持 Netscape 格式 .txt 文件</span>
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,text/plain"
            style={{ display: 'none' }}
            onChange={handleFileInput}
          />
        </div>

        {/* 分隔线 */}
        <div className="settings__divider">
          <span>或者手动粘贴</span>
        </div>

        {/* 文本粘贴区 */}
        <textarea
          className="settings__textarea"
          rows={6}
          placeholder="# Netscape HTTP Cookie File&#10;# 将 cookies.txt 内容粘贴到此处..."
          value={cookieText}
          onChange={(e) => setCookieText(e.target.value)}
        />

        <div className="settings__row">
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => submitCookies(cookieText)}
            disabled={uploading || !cookieText.trim()}
          >
            {uploading ? '上传中…' : '粘贴上传'}
          </button>
          <button
            type="button"
            className="btn btn--danger"
            onClick={handleClearCookie}
            disabled={!cookieStatus?.has_cookie}
          >
            清除 Cookie
          </button>
        </div>

        {cookieMsg && (
          <div className={`settings__msg${cookieMsg.startsWith('✅') ? ' settings__msg--ok' : ' settings__msg--err'}`}>
            {cookieMsg}
          </div>
        )}
      </section>

      {/* 代理说明 */}
      <section className="settings__section" style={{ marginTop: '32px' }}>
        <h2>全局网络代理</h2>
        <p className="settings__hint" style={{ lineHeight: '1.6' }}>
          💡 代理通过宿主机 <strong>.env</strong> 中的
          <code> HTTP_PROXY</code> / <code>HTTPS_PROXY</code> 统一配置，
          自动应用于 yt-dlp 下载、缩略图抓取等所有网络请求。
        </p>
      </section>
    </div>
  );
}

export default Settings;
