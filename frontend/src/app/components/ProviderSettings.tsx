'use client';

import { useState, useEffect, useCallback } from 'react';

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

const API_FORMATS = [
  { id: 'openai_chat', label: 'OpenAI Chat', desc: '/chat/completions' },
  { id: 'openai_responses', label: 'OpenAI Responses', desc: '/responses' },
  { id: 'anthropic', label: 'Anthropic', desc: '/v1/messages' },
  { id: 'gemini_native', label: 'Gemini Native', desc: 'google.ai' },
  { id: 'ollama_chat', label: 'Ollama Chat', desc: '/api/chat' },
];

const AUTH_FIELDS = [
  { id: 'bearer_token', label: 'Bearer Token', desc: 'Authorization: Bearer <key>' },
  { id: 'x_api_key', label: 'x-api-key', desc: 'Anthropic 原生: x-api-key: <key>' },
  { id: 'anthropic_auth_token', label: 'ANTHROPIC_AUTH_TOKEN', desc: '阿里云TokenPlan/Kimi Coding 等兼容格式' },
];

const CATEGORY_COLORS: Record<string, string> = {
  official: '#3498db',
  cn_official: '#e67e22',
  cloud_provider: '#2ecc71',
  aggregator: '#9b59b6',
  third_party: '#1abc9c',
  custom: '#e74c3c',
};

const CATEGORY_LABELS: Record<string, string> = {
  official: '官方',
  cn_official: '国产云',
  cloud_provider: '云服务',
  aggregator: '聚合',
  third_party: '第三方',
  custom: '自定义',
};

interface ProviderModel {
  name: string;
  displayName?: string;
  enabled?: boolean;
}

interface CustomProvider {
  id: string;
  name: string;
  type: string;
  category?: string;
  api_key: string;
  api_host: string;
  models: ProviderModel[];
  meta?: { api_format?: string };
  enabled?: boolean;
}

interface Preset {
  id: string;
  name: string;
  type: string;
  category: string;
  icon?: string;
  iconColor?: string;
  api_host: string;
  models: ProviderModel[];
  meta?: { api_format?: string };
}

export default function ProviderSettings() {
  const [providers, setProviders] = useState<CustomProvider[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [presetsByCategory, setPresetsByCategory] = useState<Record<string, Preset[]>>({});
  const [defaultProviderId, setDefaultProviderId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');

  // CC Switch
  const [ccswitchStatus, setCcswitchStatus] = useState<any>(null);
  const [syncingCcswitch, setSyncingCcswitch] = useState(false);
  const [autoSync, setAutoSync] = useState(true);

  // Add form
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState({ name: '', type: 'openai', api_key: '', api_host: '', model: '', api_format: 'openai_chat', auth_field: 'bearer_token' });
  const [adding, setAdding] = useState(false);

  // Test
  const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, string>>({});

  // Edit model name
  const [editingModel, setEditingModel] = useState<{ providerId: string; modelName: string } | null>(null);

  // Show presets
  const [showPresets, setShowPresets] = useState(false);

  // JSON import
  const [showJsonImport, setShowJsonImport] = useState(false);
  const [jsonText, setJsonText] = useState('');
  const [importingJson, setImportingJson] = useState(false);

  const loadCcswitchStatus = useCallback(async () => {
    try {
      const res = await fetch(apiBase() + '/providers/ccswitch-status');
      if (res.ok) {
        const data = await res.json();
        setCcswitchStatus(data);
        if (typeof data.auto_sync === 'boolean') {
          setAutoSync(data.auto_sync);
        }
      } else {
        // API 返回错误，记录状态以便调试
        setCcswitchStatus({ installed: false, error: `HTTP ${res.status}` });
      }
    } catch (err) {
      // 网络错误或后端未启动
      setCcswitchStatus({ installed: false, error: '后端连接失败' });
    }
  }, []);

  const handleCcswitchSync = async () => {
    setSyncingCcswitch(true);
    try {
      const res = await fetch(apiBase() + '/providers/ccswitch-sync', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        setMsg('✓ cc-switch 同步成功');
        load();
      } else {
        setMsg(data.detail || '同步失败');
      }
    } catch {
      setMsg('同步失败');
    } finally {
      setSyncingCcswitch(false);
    }
  };

  const handleToggleAutoSync = async () => {
    const next = !autoSync;
    try {
      const res = await fetch(apiBase() + '/providers/ccswitch-toggle-auto', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next }),
      });
      const data = await res.json();
      if (data.success) {
        setAutoSync(next);
        setMsg(`自动同步已${next ? '开启' : '关闭'}`);
      } else {
        setMsg(data.detail || '设置失败');
      }
    } catch {
      setMsg('设置失败');
    }
  };

  const handleJsonImport = async () => {
    if (!jsonText.trim()) { setMsg('请输入 JSON 内容'); return; }
    let parsed: any;
    try { parsed = JSON.parse(jsonText); } catch { setMsg('JSON 格式错误，请检查后重试'); return; }
    setImportingJson(true);
    try {
      const res = await fetch(apiBase() + '/providers/import-json', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed),
      });
      const data = await res.json();
      if (data.success) {
        setMsg(`✓ Provider "${data.provider?.name || '未知'}" 已从 JSON 导入`);
        setShowJsonImport(false);
        setJsonText('');
        load();
      } else {
        setMsg(data.detail || '导入失败');
      }
    } catch { setMsg('导入失败'); } finally { setImportingJson(false); }
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(apiBase() + '/providers/');
      if (res.ok) {
        const data = await res.json();
        setProviders(data.custom_providers || []);
        setDefaultProviderId(data.default_provider_id || null);
      }
      // Load presets
      const pRes = await fetch(apiBase() + '/providers/presets');
      if (pRes.ok) {
        const pData = await pRes.json();
        setPresets(pData.presets || []);
        setPresetsByCategory(pData.presets_by_category || {});
      }
    } catch {} finally { setLoading(false); }
    loadCcswitchStatus();
  }, [loadCcswitchStatus]);

  useEffect(() => { load(); }, [load]);

  const handleImportPreset = async (presetId: string) => {
    setAdding(true);
    try {
      const res = await fetch(apiBase() + '/providers/import-preset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preset_id: presetId }),
      });
      const data = await res.json();
      if (data.success) {
        setMsg(`预设 "${presetId}" 已导入`);
        load();
      } else {
        setMsg(data.detail || '导入失败');
      }
    } catch { setMsg('导入失败'); } finally { setAdding(false); }
  };

  const handleAdd = async () => {
    if (!addForm.name.trim()) { setMsg('Provider 名称不能为空'); return; }
    if (!addForm.api_host.trim()) { setMsg('API 地址不能为空'); return; }
    setAdding(true);
    try {
      const models: ProviderModel[] = [];
      if (addForm.model.trim()) {
        models.push({ name: addForm.model.trim(), enabled: true });
      }
      const res = await fetch(apiBase() + '/providers/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: addForm.name.trim().toLowerCase().replace(/\s+/g, '_'),
          name: addForm.name.trim(),
          type: addForm.type,
          api_key: addForm.api_key.trim(),
          api_host: addForm.api_host.trim(),
          models,
          meta: { api_format: addForm.api_format, auth_field: addForm.auth_field },
        }),
      });
      const data = await res.json();
      if (data.success) {
        setMsg(`Provider "${addForm.name}" 已添加`);
        setShowAdd(false);
        setAddForm({ name: '', type: 'openai', api_key: '', api_host: '', model: '', api_format: 'openai_chat', auth_field: 'bearer_token' });
        load();
      } else {
        setMsg(data.detail || data.error || '添加失败');
      }
    } catch { setMsg('添加失败'); } finally { setAdding(false); }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确定删除 Provider "${name}" 吗？`)) return;
    try {
      const res = await fetch(apiBase() + '/providers/' + id, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) { setMsg(`已删除 ${name}`); load(); }
      else { setMsg(data.detail || '删除失败'); }
    } catch { setMsg('删除失败'); }
  };

  const handleSetDefault = async (id: string) => {
    try {
      const res = await fetch(apiBase() + '/providers/' + id + '/default', { method: 'POST' });
      const data = await res.json();
      if (data.success) { setDefaultProviderId(id); setMsg('默认 Provider 已更新'); load(); }
      else { setMsg(data.detail || '设置失败'); }
    } catch { setMsg('设置失败'); }
  };

  const handleTest = async (provider: CustomProvider) => {
    setTesting(provider.id);
    setTestResult(prev => ({ ...prev, [provider.id]: '测试中...' }));
    try {
      const res = await fetch(apiBase() + '/providers/' + provider.id + '/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: provider.api_key,
          api_host: provider.api_host,
          model: provider.models.find(m => m.enabled)?.name || provider.models[0]?.name || '',
          api_format: provider.meta?.api_format || 'openai_chat',
        }),
      });
      const data = await res.json();
      if (data.success) {
        setTestResult(prev => ({ ...prev, [provider.id]: `✓ 成功 (${data.latency_ms}ms): ${data.response}` }));
      } else {
        setTestResult(prev => ({ ...prev, [provider.id]: `✗ ${data.error || '未知错误'}` }));
      }
    } catch {
      setTestResult(prev => ({ ...prev, [provider.id]: '✗ 连接失败' }));
    } finally {
      setTesting(null);
    }
  };

  const handleAddModel = async (providerId: string, modelName: string) => {
    if (!modelName.trim()) return;
    try {
      const res = await fetch(apiBase() + '/providers/' + providerId + '/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: modelName.trim(), enabled: true }),
      });
      const data = await res.json();
      if (data.success) { load(); }
      else { setMsg(data.detail || '添加失败'); }
    } catch {}
  };

  const handleRemoveModel = async (providerId: string, modelName: string) => {
    try {
      const res = await fetch(apiBase() + '/providers/' + providerId + '/models/' + encodeURIComponent(modelName), { method: 'DELETE' });
      const data = await res.json();
      if (data.success) load();
    } catch {}
  };

  if (loading) return <div style={{ color: '#aaa', textAlign: 'center', padding: '2rem' }}>加载中...</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
          <div>
            <span style={{ fontSize: '1.1rem', color: '#fff', fontWeight: 600 }}>🔌 多 Provider 配置</span>
            <div style={{ color: '#888', fontSize: '0.8rem', marginTop: '0.3rem' }}>
              CC Switch 风格：支持导入内置预设，自定义 API 格式（OpenAI/Anthropic/Ollama 等）
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={() => setShowJsonImport(!showJsonImport)}
              style={{ padding: '0.5rem 1rem', background: 'rgba(241,196,15,0.15)', border: '1px solid rgba(241,196,15,0.3)', borderRadius: 8, color: '#f1c40f', fontSize: '0.85rem', cursor: 'pointer', fontWeight: 600 }}
            >
              📋 JSON 导入
            </button>
            <button
              onClick={() => setShowPresets(!showPresets)}
              style={{ padding: '0.5rem 1rem', background: 'rgba(155,89,182,0.15)', border: '1px solid rgba(155,89,182,0.3)', borderRadius: 8, color: '#9b59b6', fontSize: '0.85rem', cursor: 'pointer', fontWeight: 600 }}
            >
              📦 内置预设
            </button>
            <button
              onClick={() => setShowAdd(!showAdd)}
              style={{ padding: '0.5rem 1rem', background: 'rgba(46,204,113,0.15)', border: '1px solid rgba(46,204,113,0.3)', borderRadius: 8, color: '#2ecc71', fontSize: '0.85rem', cursor: 'pointer', fontWeight: 600 }}
            >
              + 添加 Provider
            </button>
          </div>
        </div>
      </div>

      {/* CC Switch 集成 */}
      <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
              <span style={{ fontSize: '1rem', color: '#fff', fontWeight: 600 }}>🔄 CC Switch 自动同步</span>
              {ccswitchStatus?.installed ? (
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#2ecc71', display: 'inline-block' }} />
              ) : (
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#888', display: 'inline-block' }} />
              )}
            </div>
            <div style={{ color: '#888', fontSize: '0.8rem', lineHeight: 1.5 }}>
              {ccswitchStatus?.installed ? (
                <>
                  已检测到 cc-switch
                  {ccswitchStatus.db_path && <> · 数据库: {ccswitchStatus.db_path}</>}
                  {ccswitchStatus.current_provider && <> · 当前 Provider: {ccswitchStatus.current_provider}</>}
                  {ccswitchStatus.last_sync && <> · 上次同步: {ccswitchStatus.last_sync}</>}
                </>
              ) : (
                <>未检测到 cc-switch</>
              )}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            {/* Auto-sync toggle */}
            <button
              onClick={handleToggleAutoSync}
              disabled={!ccswitchStatus?.installed}
              style={{
                padding: '0.4rem 0.8rem',
                background: autoSync ? 'rgba(46,204,113,0.15)' : 'rgba(0,0,0,0.2)',
                border: `1px solid ${autoSync ? 'rgba(46,204,113,0.3)' : 'rgba(255,255,255,0.1)'}`,
                borderRadius: 8,
                color: autoSync ? '#2ecc71' : '#888',
                fontSize: '0.8rem',
                cursor: ccswitchStatus?.installed ? 'pointer' : 'not-allowed',
                fontWeight: 600,
                opacity: ccswitchStatus?.installed ? 1 : 0.5,
              }}
            >
              自动同步: {autoSync ? '开' : '关'}
            </button>
            {/* Sync now button */}
            <button
              onClick={handleCcswitchSync}
              disabled={syncingCcswitch || !ccswitchStatus?.installed}
              style={{
                padding: '0.4rem 0.9rem',
                background: !ccswitchStatus?.installed ? 'rgba(0,0,0,0.2)' : (syncingCcswitch ? 'rgba(52,152,219,0.1)' : 'rgba(52,152,219,0.15)'),
                border: '1px solid rgba(52,152,219,0.3)',
                borderRadius: 8,
                color: !ccswitchStatus?.installed ? '#666' : (syncingCcswitch ? '#3498db88' : '#3498db'),
                fontSize: '0.8rem',
                cursor: syncingCcswitch || !ccswitchStatus?.installed ? 'not-allowed' : 'pointer',
                fontWeight: 600,
              }}
              title={!ccswitchStatus?.installed ? '请先安装 cc-switch' : '立即同步 Provider 配置'}
            >
              {syncingCcswitch ? '同步中...' : (!ccswitchStatus?.installed ? '未安装' : '立即同步')}
            </button>
          </div>
        </div>
        {!ccswitchStatus?.installed && (
          <div style={{ marginTop: '1rem', padding: '0.75rem', background: 'rgba(0,0,0,0.2)', borderRadius: 8, fontSize: '0.8rem', color: '#888', lineHeight: 1.6 }}>
            <strong style={{ color: '#aaa' }}>安装 cc-switch：</strong><br />
            cc-switch 是一个跨平台 CLI 工具，用于统一管理多个 LLM Provider 配置。<br />
            安装后系统会自动检测并同步您的 Provider 设置，无需手动配置。<br />
            <code style={{ background: 'rgba(0,0,0,0.3)', padding: '0.2rem 0.4rem', borderRadius: 4, color: '#e0e0e0' }}>
              npm install -g cc-switch
            </code>
          </div>
        )}
      </div>

      {/* JSON import modal */}
      {showJsonImport && (
        <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(241,196,15,0.2)', borderRadius: 14, padding: '1.5rem' }}>
          <span style={{ fontSize: '1rem', color: '#f1c40f', fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>📋 粘贴 CC Switch JSON</span>
          <p style={{ color: '#888', fontSize: '0.8rem', marginBottom: '1rem', lineHeight: 1.5 }}>
            支持 CC Switch 配置 JSON，系统自动提取 API 地址、Key 和模型名称并创建 Provider。
          </p>
          <textarea
            value={jsonText}
            onChange={e => setJsonText(e.target.value)}
            rows={10}
            placeholder={`{\n  "env": {\n    "ANTHROPIC_BASE_URL": "https://api.kimi.com/coding/",\n    "ANTHROPIC_AUTH_TOKEN": "sk-...",\n    "ANTHROPIC_MODEL": "kimi-for-coding"\n  },\n  "model": "kimi-for-coding"\n}`}
            style={{
              width: '100%', padding: '0.75rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: 8, color: '#e0e0e0', fontSize: '0.85rem', fontFamily: 'monospace', resize: 'vertical', boxSizing: 'border-box',
            }}
          />
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
            <button onClick={handleJsonImport} disabled={importingJson} style={{ padding: '0.6rem 1.5rem', background: 'linear-gradient(135deg, #f1c40f, #e67e22)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>
              {importingJson ? '导入中...' : '确认导入'}
            </button>
            <button onClick={() => { setShowJsonImport(false); setJsonText(''); }} style={{ padding: '0.6rem 1.5rem', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#aaa', cursor: 'pointer' }}>
              取消
            </button>
          </div>
        </div>
      )}

      {/* Presets by category */}
      {showPresets && Object.keys(presetsByCategory).length > 0 && (
        <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
          <span style={{ fontSize: '1rem', color: '#fff', fontWeight: 600, display: 'block', marginBottom: '1rem' }}>📦 内置预设（点击导入）</span>
          {Object.entries(presetsByCategory).map(([cat, catPresets]) => (
            <div key={cat} style={{ marginBottom: '1rem' }}>
              <div style={{
                display: 'inline-block', padding: '0.2rem 0.6rem', borderRadius: 4, fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.5rem',
                background: `${CATEGORY_COLORS[cat] || '#666'}22`, color: CATEGORY_COLORS[cat] || '#aaa',
                border: `1px solid ${CATEGORY_COLORS[cat] || '#666'}44`,
              }}>
                {CATEGORY_LABELS[cat] || cat}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.5rem' }}>
                {catPresets.map((p: Preset) => (
                  <button
                    key={p.id}
                    onClick={() => handleImportPreset(p.id)}
                    style={{
                      padding: '0.6rem 0.8rem',
                      background: 'rgba(0,0,0,0.2)',
                      border: '1px solid rgba(255,255,255,0.1)',
                      borderRadius: 8,
                      color: '#ddd',
                      cursor: 'pointer',
                      textAlign: 'left',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.2rem',
                      transition: 'border-color 0.15s',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(155,89,182,0.5)')}
                    onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)')}
                  >
                    <span style={{ color: '#fff', fontWeight: 600, fontSize: '0.9rem' }}>{p.icon} {p.name}</span>
                    <span style={{ color: '#888', fontSize: '0.75rem' }}>{p.api_host}</span>
                    <span style={{ color: '#666', fontSize: '0.7rem' }}>
                      {p.meta?.api_format || 'openai_chat'} · {p.models.map(m => m.name).join(', ')}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add form */}
      {showAdd && (
        <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
          <span style={{ fontSize: '1rem', color: '#fff', fontWeight: 600, display: 'block', marginBottom: '1rem' }}>添加新 Provider</span>

          {/* API format selector */}
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ color: '#ddd', fontSize: '0.85rem', marginBottom: '0.5rem' }}>API 格式</div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {API_FORMATS.map(fmt => (
                <button
                  key={fmt.id}
                  onClick={() => {
                    setAddForm(f => ({ ...f, api_format: fmt.id }));
                    // Auto-set auth_field based on API format
                    if (fmt.id === 'anthropic') setAddForm(f => ({ ...f, auth_field: 'x_api_key' }));
                    else if (fmt.id === 'ollama_chat') setAddForm(f => ({ ...f, auth_field: 'bearer_token' }));
                    else setAddForm(f => ({ ...f, auth_field: 'bearer_token' }));
                  }}
                  style={{
                    padding: '0.4rem 0.7rem',
                    background: addForm.api_format === fmt.id ? 'rgba(52,152,219,0.2)' : 'rgba(0,0,0,0.2)',
                    border: `1px solid ${addForm.api_format === fmt.id ? 'rgba(52,152,219,0.5)' : 'rgba(255,255,255,0.1)'}`,
                    borderRadius: 8,
                    color: addForm.api_format === fmt.id ? '#3498db' : '#aaa',
                    cursor: 'pointer',
                    fontSize: '0.8rem',
                  }}
                >
                  {fmt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Auth field selector */}
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ color: '#ddd', fontSize: '0.85rem', marginBottom: '0.5rem' }}>认证方式</div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {AUTH_FIELDS.map(af => (
                <button
                  key={af.id}
                  onClick={() => setAddForm(f => ({ ...f, auth_field: af.id }))}
                  style={{
                    padding: '0.4rem 0.7rem',
                    background: addForm.auth_field === af.id ? 'rgba(243,156,18,0.2)' : 'rgba(0,0,0,0.2)',
                    border: `1px solid ${addForm.auth_field === af.id ? 'rgba(243,156,18,0.5)' : 'rgba(255,255,255,0.1)'}`,
                    borderRadius: 8,
                    color: addForm.auth_field === af.id ? '#f39c12' : '#aaa',
                    cursor: 'pointer',
                    fontSize: '0.8rem',
                  }}
                >
                  {af.label}
                </button>
              ))}
            </div>
            <div style={{ color: '#666', fontSize: '0.75rem', marginTop: '0.3rem' }}>
              {AUTH_FIELDS.find(af => af.id === addForm.auth_field)?.desc}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
            <input
              value={addForm.name}
              onChange={e => setAddForm(f => ({ ...f, name: e.target.value }))}
              placeholder="Provider 名称（如：阿里云百炼、硅基流动）"
              style={{ padding: '0.75rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }}
            />
            <input
              value={addForm.api_host}
              onChange={e => setAddForm(f => ({ ...f, api_host: e.target.value }))}
              placeholder="API 地址（如：https://dashscope.aliyuncs.com/compatible-mode/v1）"
              style={{ padding: '0.75rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }}
            />
            <input
              value={addForm.api_key}
              onChange={e => setAddForm(f => ({ ...f, api_key: e.target.value }))}
              type="password"
              placeholder="API Key（留空则使用环境变量）"
              style={{ padding: '0.75rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }}
            />
            <input
              value={addForm.model}
              onChange={e => setAddForm(f => ({ ...f, model: e.target.value }))}
              placeholder="默认模型名称（如：qwen-plus, gpt-4o）"
              style={{ padding: '0.75rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }}
            />
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
            <button onClick={handleAdd} disabled={adding} style={{ padding: '0.6rem 1.5rem', background: 'linear-gradient(135deg, #2ecc71, #27ae60)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>
              {adding ? '添加中...' : '确认添加'}
            </button>
            <button onClick={() => { setShowAdd(false); setAddForm({ name: '', type: 'openai', api_key: '', api_host: '', model: '', api_format: 'openai_chat', auth_field: 'bearer_token' }); }} style={{ padding: '0.6rem 1.5rem', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#aaa', cursor: 'pointer' }}>
              取消
            </button>
          </div>
        </div>
      )}

      {/* Provider list */}
      {providers.length === 0 && !showAdd && (
        <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '3rem', textAlign: 'center' }}>
          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>🔌</div>
          <div style={{ color: '#888', fontSize: '0.9rem' }}>暂无自定义 Provider，请点击「内置预设」快速导入，或「添加 Provider」手动配置</div>
        </div>
      )}

      {providers.map(provider => {
        const isDefault = provider.id === defaultProviderId;
        const apiFormat = provider.meta?.api_format || provider.type || 'openai_chat';

        return (
          <div
            key={provider.id}
            style={{
              background: isDefault ? 'rgba(46,204,113,0.05)' : 'rgba(255,255,255,0.05)',
              border: `1px solid ${isDefault ? 'rgba(46,204,113,0.3)' : 'rgba(255,255,255,0.1)'}`,
              borderRadius: 14,
              padding: '1.5rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ color: '#fff', fontWeight: 600, fontSize: '1.1rem' }}>{provider.name}</span>
                    {isDefault && (
                      <span style={{ padding: '0.15rem 0.5rem', background: 'rgba(46,204,113,0.15)', border: '1px solid rgba(46,204,113,0.3)', borderRadius: 4, color: '#2ecc71', fontSize: '0.7rem' }}>默认</span>
                    )}
                    <span style={{
                      padding: '0.15rem 0.4rem', borderRadius: 4, fontSize: '0.7rem',
                      background: `${CATEGORY_COLORS[provider.category || 'custom'] || '#666'}22`,
                      color: CATEGORY_COLORS[provider.category || 'custom'] || '#aaa',
                      border: `1px solid ${CATEGORY_COLORS[provider.category || 'custom'] || '#666'}44`,
                    }}>
                      {CATEGORY_LABELS[provider.category || 'custom'] || '自定义'}
                    </span>
                  </div>
                  <div style={{ color: '#888', fontSize: '0.8rem' }}>
                    {apiFormat} · {provider.api_host}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.4rem' }}>
                {!isDefault && (
                  <button onClick={() => handleSetDefault(provider.id)} style={{ padding: '0.3rem 0.6rem', background: 'rgba(46,204,113,0.15)', border: '1px solid rgba(46,204,113,0.3)', borderRadius: 6, color: '#2ecc71', fontSize: '0.7rem', cursor: 'pointer' }}>
                    设为默认
                  </button>
                )}
                <button onClick={() => handleTest(provider)} disabled={testing === provider.id} style={{ padding: '0.3rem 0.6rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 6, color: '#3498db', fontSize: '0.7rem', cursor: 'pointer' }}>
                  {testing === provider.id ? '测试中...' : '🧪 测试'}
                </button>
                <button onClick={() => handleDelete(provider.id, provider.name)} style={{ padding: '0.3rem 0.6rem', background: 'rgba(231,76,60,0.15)', border: '1px solid rgba(231,76,60,0.3)', borderRadius: 6, color: '#e74c3c', fontSize: '0.7rem', cursor: 'pointer' }}>
                  🗑️
                </button>
              </div>
            </div>

            {/* API Key */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.8rem', padding: '0.5rem', background: 'rgba(0,0,0,0.15)', borderRadius: 6 }}>
              <span style={{ color: '#888', fontSize: '0.8rem', minWidth: 60 }}>API Key</span>
              <code style={{ color: '#aaa', fontSize: '0.85rem', fontFamily: 'monospace' }}>
                {provider.api_key ? `${provider.api_key.slice(0, 8)}${'•'.repeat(20)}` : '(使用环境变量)'}
              </code>
            </div>

            {/* Models */}
            <div>
              <div style={{ color: '#ddd', fontSize: '0.85rem', marginBottom: '0.5rem' }}>模型</div>
              <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
                {(provider.models || []).map(m => (
                  <span
                    key={m.name}
                    style={{
                      padding: '0.3rem 0.6rem',
                      background: m.enabled ? 'rgba(52,152,219,0.15)' : 'rgba(0,0,0,0.2)',
                      border: `1px solid ${m.enabled ? 'rgba(52,152,219,0.3)' : 'rgba(255,255,255,0.08)'}`,
                      borderRadius: 6,
                      color: m.enabled ? '#3498db' : '#666',
                      fontSize: '0.8rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.3rem',
                    }}
                  >
                    {m.name}
                    <button onClick={() => handleRemoveModel(provider.id, m.name)} style={{ background: 'none', border: 'none', color: '#e74c3c', cursor: 'pointer', padding: 0, fontSize: '0.7rem' }}>✕</button>
                  </span>
                ))}
                {(!provider.models || provider.models.length === 0) && <span style={{ color: '#666', fontSize: '0.8rem' }}>暂无模型，请添加模型</span>}
              </div>
              <div style={{ display: 'flex', gap: '0.4rem' }}>
                <input
                  id={`model_add_${provider.id}`}
                  placeholder="添加模型名称"
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      const input = document.getElementById(`model_add_${provider.id}`) as HTMLInputElement;
                      if (input?.value.trim()) {
                        handleAddModel(provider.id, input.value.trim());
                        input.value = '';
                      }
                    }
                  }}
                  style={{ flex: 1, padding: '0.4rem 0.6rem', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, color: '#e0e0e0', fontSize: '0.8rem' }}
                />
              </div>
            </div>

            {/* Test result */}
            {testResult[provider.id] && (
              <div style={{ marginTop: '0.8rem', padding: '0.5rem', background: testResult[provider.id].startsWith('✓') ? 'rgba(46,204,113,0.1)' : 'rgba(231,76,60,0.1)', borderRadius: 6, fontSize: '0.85rem', color: testResult[provider.id].startsWith('✓') ? '#2ecc71' : '#e74c3c' }}>
                {testResult[provider.id]}
              </div>
            )}
          </div>
        );
      })}

      {msg && (
        <div style={{ fontSize: '0.85rem', color: msg.includes('失败') || msg.includes('不能') ? '#e74c3c' : '#2ecc71', textAlign: 'center' }}>
          {msg}
        </div>
      )}
    </div>
  );
}
