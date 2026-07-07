/**
 * Settings — 全局设置页
 *
 * 设计依据：docs/design/04-frontend-components.md §4.2 + docs/design/02-api-design.md §2.1
 *
 * 功能：
 *  - Cookies：textarea 输入 + 上传 / 清除
 *  - 代理：开关 + 协议 / host / port / 用户名 / 密码 + 连通性测试 + 保存
 */
import { useEffect, useState } from 'react';
import type { CookieStatus, ProxyConfig, ProxyTestResponse } from '../types';

const DEFAULT_PROXY: ProxyConfig = {
  enabled: false,
  scheme: 'http',
  host: '',
  port: 8080,
  username: '',
  password: '',
};

export function Settings() {
  // Cookie 状态
  const [cookieText, setCookieText] = useState('');
  const [cookieStatus, setCookieStatus] = useState<CookieStatus | null>(null);
  const [cookieMsg, setCookieMsg] = useState<string | null>(null);

  // 代理状态
  const [proxy, setProxy] = useState<ProxyConfig>(DEFAULT_PROXY);
  const [proxyMsg, setProxyMsg] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<ProxyTestResponse | null>(null);

  // 初次挂载拉取 Cookie / Proxy 当前状态
  useEffect(() => {
    fetch('/api/settings/cookies')
      .then(async (r) => (r.ok ? ((await r.json()) as CookieStatus) : null))
      .then((s) => {
        if (s) setCookieStatus(s);
      })
      .catch(() => undefined);

    fetch('/api/settings/proxy')
      .then(async (r) => (r.ok ? ((await r.json()) as Omit<ProxyConfig, 'password'>) : null))
      .then((p) => {
        if (p) {
          setProxy((prev) => ({
            ...prev,
            enabled: p.enabled,
            scheme: p.scheme,
            host: p.host,
            port: p.port,
            username: p.username,
            password: prev.password, // 密码不回显，保留当前输入
          }));
        }
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

  // === 代理操作 ===
  const handleProxyChange = <K extends keyof ProxyConfig>(
    key: K,
    value: ProxyConfig[K],
  ) => {
    setProxy((prev) => ({ ...prev, [key]: value }));
    setTestResult(null);
  };

  const handleTestProxy = async () => {
    setTesting(true);
    setProxyMsg(null);
    setTestResult(null);
    try {
      const resp = await fetch('/api/settings/proxy/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(proxy),
      });
      const data = (await resp.json()) as ProxyTestResponse;
      setTestResult(data);
      setProxyMsg(data.ok ? `✅ 连通性正常（${data.latency_ms ?? '?'} ms）` : `❌ 连通失败：${data.error ?? '未知错误'}`);
    } catch (err) {
      setProxyMsg(`❌ 测试请求失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setTesting(false);
    }
  };

  const handleSaveProxy = async () => {
    setSaving(true);
    setProxyMsg(null);
    try {
      const resp = await fetch('/api/settings/proxy', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(proxy),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setProxyMsg('✅ 代理配置已保存');
      setTestResult(null);
    } catch (err) {
      setProxyMsg(`❌ 保存失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSaving(false);
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

      {/* Proxy Section */}
      <section className="settings__section">
        <h2>代理配置</h2>
        <p className="settings__hint">
          通过代理访问 YouTube 与缩略图。可用于突破地域限制或规避 IP 风控。
        </p>

        <label className="settings__row settings__row--inline">
          <input
            type="checkbox"
            checked={proxy.enabled}
            onChange={(e) => handleProxyChange('enabled', e.target.checked)}
          />
          启用代理
        </label>

        <div className="settings__grid">
          <label className="settings__label">
            协议
            <select
              className="settings__select"
              value={proxy.scheme}
              onChange={(e) =>
                handleProxyChange('scheme', e.target.value as ProxyConfig['scheme'])
              }
            >
              <option value="http">HTTP</option>
              <option value="https">HTTPS</option>
              <option value="socks5">SOCKS5</option>
            </select>
          </label>
          <label className="settings__label">
            Host
            <input
              type="text"
              className="settings__input"
              value={proxy.host}
              onChange={(e) => handleProxyChange('host', e.target.value)}
              placeholder="127.0.0.1"
            />
          </label>
          <label className="settings__label">
            Port
            <input
              type="number"
              className="settings__input"
              value={proxy.port}
              min={1}
              max={65535}
              onChange={(e) =>
                handleProxyChange('port', Number(e.target.value) || 0)
              }
            />
          </label>
          <label className="settings__label">
            用户名
            <input
              type="text"
              className="settings__input"
              value={proxy.username}
              onChange={(e) => handleProxyChange('username', e.target.value)}
              autoComplete="off"
            />
          </label>
          <label className="settings__label">
            密码
            <input
              type="password"
              className="settings__input"
              value={proxy.password}
              onChange={(e) => handleProxyChange('password', e.target.value)}
              autoComplete="off"
              placeholder="（保留旧值 / 留空则不修改）"
            />
          </label>
        </div>

        <div className="settings__row">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={handleTestProxy}
            disabled={testing || !proxy.host}
          >
            {testing ? '测试中…' : '测试连通性'}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={handleSaveProxy}
            disabled={saving}
          >
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
        {testResult && (
          <div className="settings__test-result">
            <span>状态码：{testResult.status_code ?? '—'}</span>
            <span>延迟：{testResult.latency_ms ?? '—'} ms</span>
            {testResult.error && <span>错误：{testResult.error}</span>}
          </div>
        )}
        {proxyMsg && <div className="settings__msg">{proxyMsg}</div>}
      </section>
    </div>
  );
}

export default Settings;