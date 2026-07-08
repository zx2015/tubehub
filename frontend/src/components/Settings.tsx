/**
 * Settings — 全局设置页 (极简自愈版)
 *
 * 移除前端代理配置（已重构至系统环境变量 .env 全局代理，由 Docker 自愈容器隐式捕获）。
 */
import { useEffect, useState } from 'react';
import type { CookieStatus } from '../types';

export function Settings() {
  // Cookie 状态
  const [cookieText, setCookieText] = useState('');
  const [cookieStatus, setCookieStatus] = useState<CookieStatus | null>(null);
  const [cookieMsg, setCookieMsg] = useState<string | null>(null);

  // 初次挂载拉取 Cookie 当前状态
  useEffect(() => {
    fetch('/api/settings/cookies')
      .then(async (r) => (r.ok ? ((await r.json()) as CookieStatus) : null))
      .then((s) => {
        if (s) setCookieStatus(s);
      })
      .catch(() => undefined);
  }, []);

  // === Cookie 操作 ===
  const handleUploadCookie = async () => {
    if (!cookieText.trim()) {
      setCookieMsg('请粘贴 Cookie 内容');
      return;
    }
    setCookieMsg(null);
    try {
      const resp = await fetch('/api/settings/cookies', {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain' },
        body: cookieText,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const status = (await resp.json()) as CookieStatus;
      setCookieStatus(status);
      setCookieText('');
      setCookieMsg('✅ Cookie 已上传');
    } catch (err) {
      setCookieMsg(`❌ 上传失败：${err instanceof Error ? err.message : String(err)}`);
    }
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
          当下载受限视频（如年龄限制、会员内容）时，可粘贴浏览器导出的 Netscape 格式 Cookie。
        </p>
        <div className="settings__cookie-status">
          状态：
          {cookieStatus?.has_cookie ? (
            <strong className="settings__status--ok">
              {' '}已配置 ({cookieStatus.file_size ?? '?'} 字节)
            </strong>
          ) : (
            <strong className="settings__status--muted"> 未配置</strong>
          )}
        </div>
        <textarea
          className="settings__textarea"
          rows={8}
          placeholder="# Netscape HTTP Cookie File..."
          value={cookieText}
          onChange={(e) => setCookieText(e.target.value)}
        />
        <div className="settings__row">
          <button
            type="button"
            className="btn btn--primary"
            onClick={handleUploadCookie}
          >
            上传
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={handleClearCookie}
            disabled={!cookieStatus?.has_cookie}
          >
            清除
          </button>
        </div>
        {cookieMsg && <div className="settings__msg">{cookieMsg}</div>}
      </section>

      {/* Info Section */}
      <section className="settings__section" style={{ marginTop: '32px' }}>
        <h2>全局网络代理</h2>
        <p className="settings__hint" style={{ lineHeight: '1.6' }}>
          💡 代理配置现已升级：您可以直接在宿主机 <strong>.env</strong> 中通过 
          <code> HTTP_PROXY</code> 与 <code> HTTPS_PROXY</code> 统一配置系统级代理。<br />
          容器启动时会全自动应用于 <strong>Git 更新</strong>、<strong>Pip 依赖更新</strong>、
          <strong>yt-dlp 视频流下载</strong>、以及 <strong>缩略图代理缓存</strong>，实现了全系统的自愈与统一。
        </p>
      </section>
    </div>
  );
}

export default Settings;