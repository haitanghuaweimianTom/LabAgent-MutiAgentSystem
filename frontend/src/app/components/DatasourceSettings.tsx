'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiBase } from '@/lib/api';
import { useTheme } from '@/hooks/useTheme';

interface SchemaField {
  name: string;
  label: string;
  type: string;
  placeholder?: string;
  hint?: string;
}
interface Schema {
  label: string;
  icon: string;
  fields: SchemaField[];
}
interface KeyEntry {
  label: string;
  icon: string;
  enabled: boolean;
  configured: boolean;
  fields: Record<string, string>;
  updated_at?: string;
}
interface ProxyStatus {
  detected: string | null;
  source: string | null;
  use_proxy: boolean;
  manual_proxy: string;
  manual_enabled: boolean;
  socks_supported: boolean;
  updated_at?: string;
}

const SOURCE_EMOJI: Record<string, string> = {
  github: '🐙',
  kaggle: '🏆',
  huggingface: '🤗',
};

export default function DatasourceSettings() {
  const { theme } = useTheme();
  const dark = theme === 'dark';
  const [schemas, setSchemas] = useState<Record<string, Schema>>({});
  const [keys, setKeys] = useState<Record<string, KeyEntry>>({});
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');

  const [editFields, setEditFields] = useState<Record<string, Record<string, string>>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});

  // 代理
  const [proxyStatus, setProxyStatus] = useState<ProxyStatus | null>(null);
  const [manualProxy, setManualProxy] = useState('');
  const [manualEnabled, setManualEnabled] = useState(false);
  const [useProxy, setUseProxy] = useState(true);
  const [proxyTesting, setProxyTesting] = useState(false);
  const [proxyTestResult, setProxyTestResult] = useState('');
  const [proxySaving, setProxySaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sRes, kRes] = await Promise.all([
        fetch(apiBase() + '/datasources/schemas'),
        fetch(apiBase() + '/datasources/keys'),
      ]);
      if (sRes.ok) setSchemas((await sRes.json()).schemas || {});
      if (kRes.ok) setKeys((await kRes.json()).keys || {});
    } catch {
    } finally {
      setLoading(false);
    }
    try {
      const r = await fetch(apiBase() + '/proxy/status');
      if (r.ok) {
        const ps = await r.json();
        setProxyStatus(ps);
        setManualProxy(ps.manual_proxy || '');
        setManualEnabled(!!ps.manual_enabled);
        setUseProxy(ps.use_proxy !== false);
      }
    } catch {
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const setField = (source: string, name: string, val: string) => {
    setEditFields((prev) => ({
      ...prev,
      [source]: { ...(prev[source] || {}), [name]: val },
    }));
  };

  const handleSave = async (source: string) => {
    const typed = editFields[source] || {};
    const nonEmpty: Record<string, string> = {};
    Object.entries(typed).forEach(([k, v]) => {
      if (v && v.trim()) nonEmpty[k] = v.trim();
    });
    if (Object.keys(nonEmpty).length === 0) {
      setMsg(`请填写 ${schemas[source]?.label || source} 的至少一个字段`);
      return;
    }
    setSaving(source);
    try {
      const res = await fetch(apiBase() + '/datasources/keys/' + source, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fields: nonEmpty, enabled: true }),
      });
      const data = await res.json();
      if (data.saved) {
        setMsg(`✓ ${schemas[source]?.label || source} key 已保存`);
        setEditFields((prev) => ({ ...prev, [source]: {} }));
        load();
      } else {
        setMsg(data.detail || '保存失败');
      }
    } catch {
      setMsg('保存失败');
    } finally {
      setSaving(null);
    }
  };

  const handleDelete = async (source: string) => {
    if (!confirm(`确定删除 ${schemas[source]?.label || source} 的 key 吗？`)) return;
    try {
      await fetch(apiBase() + '/datasources/keys/' + source, { method: 'DELETE' });
      setMsg(`已删除 ${schemas[source]?.label || source} key`);
      setEditFields((prev) => ({ ...prev, [source]: {} }));
      load();
    } catch {
      setMsg('删除失败');
    }
  };

  const handleTest = async (source: string) => {
    setTesting(source);
    setTestResults((prev) => ({ ...prev, [source]: '测试中...' }));
    try {
      const res = await fetch(apiBase() + '/datasources/keys/' + source + '/test', {
        method: 'POST',
      });
      const data = await res.json();
      setTestResults((prev) => ({
        ...prev,
        [source]: (data.ok ? '✓ ' : '✗ ') + (data.message || ''),
      }));
    } catch {
      setTestResults((prev) => ({ ...prev, [source]: '✗ 连接失败' }));
    } finally {
      setTesting(null);
    }
  };

  const handleSaveProxy = async () => {
    setProxySaving(true);
    try {
      const res = await fetch(apiBase() + '/proxy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          manual_proxy: manualProxy,
          manual_enabled: manualEnabled,
          use_proxy: useProxy,
        }),
      });
      const data = await res.json();
      setProxyStatus(data);
      setMsg('✓ 代理设置已保存');
    } catch {
      setMsg('代理设置失败');
    } finally {
      setProxySaving(false);
    }
  };

  const handleClearProxy = async () => {
    try {
      const res = await fetch(apiBase() + '/proxy', { method: 'DELETE' });
      const data = await res.json();
      setProxyStatus(data);
      setManualProxy('');
      setManualEnabled(false);
      setMsg('已清除手动代理');
    } catch {
      setMsg('清除失败');
    }
  };

  const handleTestProxy = async () => {
    setProxyTesting(true);
    setProxyTestResult('测试中...');
    try {
      const res = await fetch(apiBase() + '/proxy/test', { method: 'POST' });
      const data = await res.json();
      const extra = data.direct_status ? ` （直连 HTTP ${data.direct_status}）` : '';
      setProxyTestResult((data.ok ? '✓ ' : '✗ ') + (data.message || '') + extra);
    } catch {
      setProxyTestResult('✗ 测试失败');
    } finally {
      setProxyTesting(false);
    }
  };

  const cardStyle: React.CSSProperties = {
    background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: 14,
    padding: '1.5rem',
  };
  const inputStyle: React.CSSProperties = {
    padding: '0.6rem 0.75rem',
    background: 'rgba(0,0,0,0.3)',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: 8,
    color: '#e0e0e0',
    fontSize: '0.85rem',
    width: '100%',
    boxSizing: 'border-box',
  };
  const btn = (
    bg: string,
    border: string,
    color: string,
    opts: Partial<React.CSSProperties> = {},
  ): React.CSSProperties => ({
    padding: '0.4rem 0.8rem',
    background: bg,
    border: `1px solid ${border}`,
    borderRadius: 8,
    color,
    fontSize: '0.8rem',
    cursor: 'pointer',
    fontWeight: 600,
    ...opts,
  });

  if (loading) {
    return (
      <div style={{ color: dark ? '#cbd5e1' : '#aaa', textAlign: 'center', padding: '2rem' }}>
        加载中...
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* 代理卡 */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
          <div>
            <span style={{ fontSize: '1.1rem', color: '#fff', fontWeight: 600 }}>🌐 网络代理</span>
            <div style={{ color: dark ? '#94a3b8' : '#888', fontSize: '0.8rem', marginTop: '0.3rem' }}>
              自动检测系统代理（gsettings/环境变量/scutil/注册表）；仅用于「取数据」，不影响 LLM 调用
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: proxyStatus?.detected ? '#2ecc71' : '#666',
                display: 'inline-block',
              }}
            />
            <span style={{ color: dark ? '#cbd5e1' : '#aaa', fontSize: '0.8rem' }}>
              {proxyStatus?.detected ? `已检测: ${proxyStatus.detected}` : '未检测到代理'}
            </span>
          </div>
        </div>

        <div style={{ color: dark ? '#94a3b8' : '#888', fontSize: '0.78rem', marginBottom: '0.8rem' }}>
          来源: {proxyStatus?.source || '—'} · SOCKS 支持: {proxyStatus?.socks_supported ? '是' : '否'}
          {proxyStatus?.updated_at ? ` · 更新于 ${proxyStatus.updated_at.slice(0, 19)}` : ''}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: dark ? '#cbd5e1' : '#ddd', fontSize: '0.85rem' }}>
            <input type="checkbox" checked={useProxy} onChange={(e) => setUseProxy(e.target.checked)} />
            启用代理（关闭则取数据全部走直连）
          </label>

          <div>
            <div style={{ color: dark ? '#e2e8f0' : '#ddd', fontSize: '0.8rem', marginBottom: '0.3rem' }}>
              手动覆盖代理（留空则用自动检测的值）
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <input
                value={manualProxy}
                onChange={(e) => setManualProxy(e.target.value)}
                placeholder="http://127.0.0.1:7890 或 socks5://127.0.0.1:1080"
                style={inputStyle}
              />
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', color: dark ? '#cbd5e1' : '#ddd', fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
                <input
                  type="checkbox"
                  checked={manualEnabled}
                  onChange={(e) => setManualEnabled(e.target.checked)}
                />
                启用手动
              </label>
            </div>
            <div style={{ color: dark ? '#94a3b8' : '#666', fontSize: '0.72rem', marginTop: '0.3rem' }}>
              采集逻辑：每个数据请求先直连，仅当直连连接失败时才回退到代理——直连可达的源（GitHub/hf-mirror/Kaggle）零影响。
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button
              onClick={handleSaveProxy}
              disabled={proxySaving}
              style={btn('rgba(46,204,113,0.15)', 'rgba(46,204,113,0.3)', '#2ecc71')}
            >
              {proxySaving ? '保存中...' : '💾 保存代理设置'}
            </button>
            <button
              onClick={handleTestProxy}
              disabled={proxyTesting}
              style={btn('rgba(52,152,219,0.15)', 'rgba(52,152,219,0.3)', '#3498db')}
            >
              {proxyTesting ? '测试中...' : '🧪 测试代理'}
            </button>
            <button onClick={handleClearProxy} style={btn('rgba(231,76,60,0.15)', 'rgba(231,76,60,0.3)', '#e74c3c')}>
              清除手动
            </button>
          </div>

          {proxyTestResult && (
            <div
              style={{
                padding: '0.5rem 0.75rem',
                background: proxyTestResult.startsWith('✓') ? 'rgba(46,204,113,0.1)' : 'rgba(231,76,60,0.1)',
                borderRadius: 6,
                fontSize: '0.82rem',
                color: proxyTestResult.startsWith('✓') ? '#2ecc71' : '#e74c3c',
              }}
            >
              {proxyTestResult}
            </div>
          )}
        </div>
      </div>

      {/* 数据源 Key 卡 */}
      <div style={cardStyle}>
        <span style={{ fontSize: '1.1rem', color: '#fff', fontWeight: 600 }}>🗃️ 数据源 API Key</span>
        <div style={{ color: dark ? '#94a3b8' : '#888', fontSize: '0.8rem', marginTop: '0.3rem' }}>
          配置 GitHub / Kaggle / HuggingFace 凭证，让系统用你的 key 拉取数据集。GitHub 与 HuggingFace 不填 key 也能用（匿名/镜像）。
        </div>
      </div>

      {Object.keys(schemas).length === 0 && (
        <div style={cardStyle}>
          <div style={{ color: dark ? '#94a3b8' : '#888', fontSize: '0.9rem', textAlign: 'center' }}>
            无法加载数据源 schema，请确认后端已启动。
          </div>
        </div>
      )}

      {Object.entries(schemas).map(([source, schema]) => {
        const entry = keys[source] || { label: schema.label, icon: schema.icon, enabled: false, configured: false, fields: {} };
        return (
          <div key={source} style={{ ...cardStyle, borderColor: entry.configured ? 'rgba(46,204,113,0.3)' : 'rgba(255,255,255,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.8rem' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontSize: '1.3rem' }}>{SOURCE_EMOJI[source] || '📦'}</span>
                  <span style={{ color: '#fff', fontWeight: 600, fontSize: '1.05rem' }}>{schema.label}</span>
                  {entry.configured && (
                    <span style={{ padding: '0.15rem 0.5rem', background: 'rgba(46,204,113,0.15)', border: '1px solid rgba(46,204,113,0.3)', borderRadius: 4, color: '#2ecc71', fontSize: '0.7rem' }}>
                      已配置
                    </span>
                  )}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.4rem' }}>
                <button
                  onClick={() => handleTest(source)}
                  disabled={testing === source}
                  style={btn('rgba(52,152,219,0.15)', 'rgba(52,152,219,0.3)', '#3498db', { fontSize: '0.72rem' })}
                >
                  {testing === source ? '测试中...' : '🧪 测试'}
                </button>
                {entry.configured && (
                  <button
                    onClick={() => handleDelete(source)}
                    style={btn('rgba(231,76,60,0.15)', 'rgba(231,76,60,0.3)', '#e74c3c', { fontSize: '0.72rem' })}
                  >
                    🗑️ 删除
                  </button>
                )}
              </div>
            </div>

            {/* 当前已存（脱敏） */}
            {entry.configured && (
              <div style={{ marginBottom: '0.8rem', padding: '0.5rem 0.6rem', background: 'rgba(0,0,0,0.15)', borderRadius: 6 }}>
                {schema.fields.map((f) => (
                  <div key={f.name} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem', marginBottom: '0.2rem' }}>
                    <span style={{ color: dark ? '#94a3b8' : '#888', minWidth: 90 }}>{f.label}</span>
                    <code style={{ color: dark ? '#cbd5e1' : '#aaa', fontFamily: 'monospace' }}>{entry.fields[f.name] || '(未设置)'}</code>
                  </div>
                ))}
              </div>
            )}

            {/* 输入新值 */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              {schema.fields.map((f) => (
                <div key={f.name}>
                  <div style={{ color: dark ? '#e2e8f0' : '#ddd', fontSize: '0.8rem', marginBottom: '0.25rem' }}>{f.label}</div>
                  <input
                    type={f.type === 'password' ? 'password' : 'text'}
                    value={(editFields[source] || {})[f.name] || ''}
                    onChange={(e) => setField(source, f.name, e.target.value)}
                    placeholder={f.placeholder || ''}
                    style={inputStyle}
                  />
                  {f.hint && (
                    <div style={{ color: dark ? '#94a3b8' : '#666', fontSize: '0.72rem', marginTop: '0.25rem' }}>{f.hint}</div>
                  )}
                </div>
              ))}
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  onClick={() => handleSave(source)}
                  disabled={saving === source}
                  style={btn('rgba(46,204,113,0.15)', 'rgba(46,204,113,0.3)', '#2ecc71', { fontSize: '0.75rem' })}
                >
                  {saving === source ? '保存中...' : '💾 保存'}
                </button>
              </div>
            </div>

            {testResults[source] && (
              <div
                style={{
                  marginTop: '0.8rem',
                  padding: '0.5rem 0.6rem',
                  background: testResults[source].startsWith('✓') ? 'rgba(46,204,113,0.1)' : 'rgba(231,76,60,0.1)',
                  borderRadius: 6,
                  fontSize: '0.82rem',
                  color: testResults[source].startsWith('✓') ? '#2ecc71' : '#e74c3c',
                }}
              >
                {testResults[source]}
              </div>
            )}
          </div>
        );
      })}

      {msg && (
        <div style={{ fontSize: '0.85rem', color: msg.includes('失败') || msg.includes('请填') ? '#e74c3c' : '#2ecc71', textAlign: 'center' }}>
          {msg}
        </div>
      )}
    </div>
  );
}
