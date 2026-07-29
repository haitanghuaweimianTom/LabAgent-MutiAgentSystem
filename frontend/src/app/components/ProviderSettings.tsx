'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiBase } from '@/lib/api';

// API 格式和认证字段从后端动态加载
interface ApiFormat { id: string; label: string; desc: string; }
interface AuthField { id: string; label: string; desc: string; }

const CATEGORY_LABELS: Record<string, string> = {
  official: '官方',
  cn_official: '国产云',
  cloud_provider: '云服务',
  aggregator: '聚合',
  third_party: '第三方',
  custom: '自定义',
};

// Geist 单色：分类标签统一用 primary 单色，不再用 6 色彩虹。
const CATEGORY_LABEL = (cat: string) => CATEGORY_LABELS[cat] || '自定义';

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

// 卡片容器（Geist 单色：浅色白卡/深色深卡，自适应）
const cardClass = 'bg-card border border-border rounded-xl p-5';

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
        setCcswitchStatus({ installed: false, error: `HTTP ${res.status}` });
      }
    } catch (err) {
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

  // 动态加载 API 格式和认证字段
  const [apiFormats, setApiFormats] = useState<ApiFormat[]>([]);
  const [authFields, setAuthFields] = useState<AuthField[]>([]);

  // 加载 API 格式和认证字段
  const loadApiFormats = useCallback(async () => {
    try {
      const [fmtRes, authRes] = await Promise.all([
        fetch(apiBase() + '/providers/api-formats'),
        fetch(apiBase() + '/providers/auth-fields'),
      ]);
      if (fmtRes.ok) {
        const data = await fmtRes.json();
        setApiFormats(data.formats || []);
      }
      if (authRes.ok) {
        const data = await authRes.json();
        setAuthFields(data.fields || []);
      }
    } catch {
      // 如果后端不支持，使用空数组
    }
  }, []);

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
    loadApiFormats();
  }, [loadCcswitchStatus, loadApiFormats]);

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
      // 自动检测正确的 api_format
      let apiFormat = provider.meta?.api_format || 'openai_chat';
      // 如果 provider 类型是 anthropic 但 host 包含 kimi，使用 anthropic_messages (OpenAI兼容模式)
      if (provider.type === 'anthropic' && provider.api_host.includes('kimi')) {
        apiFormat = 'anthropic_messages';
      }

      const res = await fetch(apiBase() + '/providers/' + provider.id + '/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: provider.api_key,
          api_host: provider.api_host,
          model: provider.models.find(m => m.enabled)?.name || provider.models[0]?.name || '',
          api_format: apiFormat,
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

  const handleAutoDetectModels = async (providerId: string) => {
    setMsg('正在自动获取模型列表...');
    try {
      const res = await fetch(apiBase() + '/providers/' + providerId + '/auto-detect-models', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        setMsg(`✓ 自动检测到 ${data.models.length} 个模型: ${data.models.join(', ')}`);
        load();
      } else {
        setMsg(data.message || '自动获取失败，请手动添加模型');
      }
    } catch {
      setMsg('自动获取失败，请手动添加模型');
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

  if (loading) return <div className="text-center p-8 text-muted-foreground text-sm">加载中...</div>;

  // 语义色按钮样式（Geist 单色）
  const btnBase = 'inline-flex items-center justify-center gap-1.5 rounded-lg cursor-pointer font-semibold transition-opacity duration-150 hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed';
  const btnPrimary = `${btnBase} py-2 px-4 text-sm bg-primary text-primary-foreground`;
  const btnSuccess = `${btnBase} py-2 px-4 text-sm bg-success/10 text-success border border-success/20 hover:bg-success/15`;
  const btnInfo = `${btnBase} py-2 px-4 text-sm bg-primary/10 text-primary border border-primary/20 hover:bg-primary/15`;
  const btnDanger = `${btnBase} py-2 px-4 text-sm bg-error/10 text-error border border-error/20 hover:bg-error/15`;
  const btnWarning = `${btnBase} py-2 px-4 text-sm bg-warning/10 text-warning border border-warning/20 hover:bg-warning/15`;
  const btnPurple = `${btnBase} py-2 px-4 text-sm bg-primary/10 text-primary border border-primary/20 hover:bg-primary/15`;
  const btnGhost = `${btnBase} py-2 px-4 text-sm bg-muted text-muted-foreground border border-border hover:bg-muted/70`;
  // 小尺寸按钮（列表内操作：测试/删除/设为默认/自动获取）
  const btnSm = (extra: string) => `${btnBase} py-1.5 px-3 text-xs rounded-md ${extra}`;
  const btnSmInfo = btnSm('bg-primary/10 text-primary border border-primary/20 hover:bg-primary/15');
  const btnSmSuccess = btnSm('bg-success/10 text-success border border-success/20 hover:bg-success/15');
  const btnSmDanger = btnSm('bg-error/10 text-error border border-error/20 hover:bg-error/15');
  const btnSmPurple = btnSm('bg-primary/10 text-primary border border-primary/20 hover:bg-primary/15');

  const inputClass = 'flex-1 py-2 px-3 bg-muted border border-border rounded-md text-foreground text-sm focus:outline-none focus:border-primary placeholder:text-muted-foreground';

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className={cardClass}>
        <div className="flex justify-between items-center mb-2">
          <div>
            <span className="text-lg text-foreground font-semibold">🔌 多 Provider 配置</span>
            <div className="text-muted-foreground text-sm mt-1">
              CC Switch 风格：支持导入内置预设，自定义 API 格式（OpenAI/Anthropic/Ollama 等）
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setShowJsonImport(!showJsonImport)} className={btnWarning}>📋 JSON 导入</button>
            <button onClick={() => setShowPresets(!showPresets)} className={btnPurple}>📦 内置预设</button>
            <button onClick={() => setShowAdd(!showAdd)} className={btnSuccess}>+ 添加 Provider</button>
          </div>
        </div>
      </div>

      {/* CC switch 集成 */}
      <div className={cardClass}>
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-base text-foreground font-semibold">🔄 CC Switch 自动同步</span>
              {ccswitchStatus?.installed ? (
                <span className="w-2 h-2 rounded-full bg-success inline-block" />
              ) : (
                <span className="w-2 h-2 rounded-full bg-muted-foreground inline-block" />
              )}
            </div>
            <div className="text-muted-foreground text-sm leading-relaxed">
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
          <div className="flex items-center gap-3">
            <button
              onClick={handleToggleAutoSync}
              disabled={!ccswitchStatus?.installed}
              className={autoSync ? btnSuccess : btnGhost}
            >
              自动同步: {autoSync ? '开' : '关'}
            </button>
            <button
              onClick={handleCcswitchSync}
              disabled={syncingCcswitch || !ccswitchStatus?.installed}
              className={btnInfo}
              title={!ccswitchStatus?.installed ? '请先安装 cc-switch' : '立即同步 Provider 配置'}
            >
              {syncingCcswitch ? '同步中...' : (!ccswitchStatus?.installed ? '未安装' : '立即同步')}
            </button>
          </div>
        </div>
        {!ccswitchStatus?.installed && (
          <div className="mt-4 p-3 bg-muted rounded-md text-sm text-muted-foreground leading-relaxed">
            <strong className="text-foreground">安装 cc-switch：</strong><br />
            cc-switch 是一个跨平台 CLI 工具，用于统一管理多个 LLM Provider 配置。<br />
            安装后系统会自动检测并同步您的 Provider 设置，无需手动配置。<br />
            <code className="bg-card border border-border px-1.5 py-0.5 rounded text-foreground">
              npm install -g cc-switch
            </code>
          </div>
        )}
      </div>

      {/* JSON import modal */}
      {showJsonImport && (
        <div className="bg-card border border-warning/20 rounded-xl p-5">
          <span className="text-base text-warning font-semibold block mb-2">📋 粘贴 CC Switch JSON</span>
          <p className="text-muted-foreground text-sm mb-4 leading-relaxed">
            支持 CC Switch 配置 JSON，系统自动提取 API 地址、Key 和模型名称并创建 Provider。
          </p>
          <textarea
            value={jsonText}
            onChange={e => setJsonText(e.target.value)}
            rows={10}
            placeholder={`{\n  "env": {\n    "ANTHROPIC_BASE_URL": "https://api.kimi.com/coding/",\n    "ANTHROPIC_AUTH_TOKEN": "sk-...",\n    "ANTHROPIC_MODEL": "kimi-for-coding"\n  },\n  "model": "kimi-for-coding"\n}`}
            className="w-full p-3 bg-muted border border-border rounded-md text-foreground text-sm font-mono resize-y box-border focus:outline-none focus:border-primary placeholder:text-muted-foreground"
          />
          <div className="flex gap-2 mt-4">
            <button onClick={handleJsonImport} disabled={importingJson} className={btnPrimary}>
              {importingJson ? '导入中...' : '确认导入'}
            </button>
            <button onClick={() => { setShowJsonImport(false); setJsonText(''); }} className={btnGhost}>
              取消
            </button>
          </div>
        </div>
      )}

      {/* Presets by category */}
      {showPresets && Object.keys(presetsByCategory).length > 0 && (
        <div className={cardClass}>
          <span className="text-base text-foreground font-semibold block mb-4">📦 内置预设（点击导入）</span>
          {Object.entries(presetsByCategory).map(([cat, catPresets]) => (
            <div key={cat} className="mb-4">
              <div className="inline-block py-0.5 px-2.5 rounded text-xs font-semibold mb-2 bg-primary/10 text-primary border border-primary/20">
                {CATEGORY_LABEL(cat)}
              </div>
              <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
                {catPresets.map((p: Preset) => (
                  <button
                    key={p.id}
                    onClick={() => handleImportPreset(p.id)}
                    className="p-2.5 bg-muted border border-border rounded-md text-foreground cursor-pointer text-left flex flex-col gap-1 transition-colors hover:border-primary/40"
                  >
                    <span className="text-foreground font-semibold text-sm">{p.icon} {p.name}</span>
                    <span className="text-muted-foreground text-xs">{p.api_host}</span>
                    <span className="text-muted-foreground text-xs">
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
        <div className={cardClass}>
          <span className="text-base text-foreground font-semibold block mb-4">添加新 Provider</span>

          {/* API format selector */}
          <div className="mb-4">
            <div className="text-foreground text-sm mb-2">API 格式</div>
            <div className="flex gap-2 flex-wrap">
              {(apiFormats.length > 0 ? apiFormats : [
                { id: 'openai_chat', label: 'OpenAI Chat', desc: '/chat/completions' },
                { id: 'openai_responses', label: 'OpenAI Responses', desc: '/responses' },
                { id: 'anthropic', label: 'Anthropic', desc: '/v1/messages' },
                { id: 'anthropic_messages', label: 'Anthropic (OpenAI兼容)', desc: '/chat/completions' },
                { id: 'gemini_native', label: 'Gemini Native', desc: 'google.ai' },
                { id: 'ollama_chat', label: 'Ollama Chat', desc: '/api/chat' },
              ]).map(fmt => (
                <button
                  key={fmt.id}
                  onClick={() => {
                    setAddForm(f => ({ ...f, api_format: fmt.id }));
                    if (fmt.id === 'anthropic') setAddForm(f => ({ ...f, auth_field: 'x_api_key' }));
                    else if (fmt.id === 'ollama_chat') setAddForm(f => ({ ...f, auth_field: 'bearer_token' }));
                    else setAddForm(f => ({ ...f, auth_field: 'bearer_token' }));
                  }}
                  className={addForm.api_format === fmt.id ? btnInfo : btnGhost}
                >
                  {fmt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Auth field selector */}
          <div className="mb-4">
            <div className="text-foreground text-sm mb-2">认证方式</div>
            <div className="flex gap-2 flex-wrap">
              {(authFields.length > 0 ? authFields : [
                { id: 'bearer_token', label: 'Bearer Token', desc: 'Authorization: Bearer <key>' },
                { id: 'x_api_key', label: 'x-api-key', desc: 'Anthropic 原生: x-api-key: <key>' },
                { id: 'anthropic_auth_token', label: 'ANTHROPIC_AUTH_TOKEN', desc: '阿里云TokenPlan/Kimi Coding 等兼容格式' },
              ]).map(af => (
                <button
                  key={af.id}
                  onClick={() => setAddForm(f => ({ ...f, auth_field: af.id }))}
                  className={addForm.auth_field === af.id ? btnWarning : btnGhost}
                >
                  {af.label}
                </button>
              ))}
            </div>
            <div className="text-muted-foreground text-xs mt-1.5">
              {(authFields.length > 0 ? authFields : [
                { id: 'bearer_token', label: 'Bearer Token', desc: 'Authorization: Bearer <key>' },
                { id: 'x_api_key', label: 'x-api-key', desc: 'Anthropic 原生: x-api-key: <key>' },
                { id: 'anthropic_auth_token', label: 'ANTHROPIC_AUTH_TOKEN', desc: '阿里云TokenPlan/Kimi Coding 等兼容格式' },
              ]).find(af => af.id === addForm.auth_field)?.desc}
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <input
              value={addForm.name}
              onChange={e => setAddForm(f => ({ ...f, name: e.target.value }))}
              placeholder="Provider 名称（如：阿里云百炼、硅基流动）"
              className={inputClass}
            />
            <input
              value={addForm.api_host}
              onChange={e => setAddForm(f => ({ ...f, api_host: e.target.value }))}
              placeholder="API 地址（如：https://dashscope.aliyuncs.com/compatible-mode/v1）"
              className={inputClass}
            />
            <input
              value={addForm.api_key}
              onChange={e => setAddForm(f => ({ ...f, api_key: e.target.value }))}
              type="password"
              placeholder="API Key（留空则使用环境变量）"
              className={inputClass}
            />
            <input
              value={addForm.model}
              onChange={e => setAddForm(f => ({ ...f, model: e.target.value }))}
              placeholder="默认模型名称（如：qwen-plus, gpt-4o）"
              className={inputClass}
            />
          </div>
          <div className="flex gap-2 mt-4">
            <button onClick={handleAdd} disabled={adding} className={btnPrimary}>
              {adding ? '添加中...' : '确认添加'}
            </button>
            <button onClick={() => { setShowAdd(false); setAddForm({ name: '', type: 'openai', api_key: '', api_host: '', model: '', api_format: 'openai_chat', auth_field: 'bearer_token' }); }} className={btnGhost}>
              取消
            </button>
          </div>
        </div>
      )}

      {/* Provider list */}
      {providers.length === 0 && !showAdd && (
        <div className="bg-card border border-border rounded-xl p-12 text-center">
          <div className="text-2xl mb-2">🔌</div>
          <div className="text-muted-foreground text-sm">暂无自定义 Provider，请点击「内置预设」快速导入，或「添加 Provider」手动配置</div>
        </div>
      )}

      {providers.map(provider => {
        const isDefault = provider.id === defaultProviderId;
        const apiFormat = provider.meta?.api_format || provider.type || 'openai_chat';

        return (
          <div
            key={provider.id}
            className={`border rounded-xl p-5 ${isDefault ? 'bg-success/5 border-success/30' : 'bg-card border-border'}`}
          >
            <div className="flex justify-between items-start mb-4">
              <div className="flex items-center gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-foreground font-semibold text-lg">{provider.name}</span>
                    {isDefault && (
                      <span className="py-0.5 px-2 bg-success/10 border border-success/20 rounded text-success text-xs">默认</span>
                    )}
                    <span className="py-0.5 px-1.5 rounded text-xs bg-primary/10 text-primary border border-primary/20">
                      {CATEGORY_LABEL(provider.category || 'custom')}
                    </span>
                  </div>
                  <div className="text-muted-foreground text-sm">
                    {apiFormat} · {provider.api_host}
                  </div>
                </div>
              </div>
              <div className="flex gap-1.5">
                {!isDefault && (
                  <button onClick={() => handleSetDefault(provider.id)} className={btnSmSuccess}>
                    设为默认
                  </button>
                )}
                <button onClick={() => handleTest(provider)} disabled={testing === provider.id} className={btnSmInfo}>
                  {testing === provider.id ? '测试中...' : '🧪 测试'}
                </button>
                <button onClick={() => handleDelete(provider.id, provider.name)} className={btnSmDanger}>
                  🗑️
                </button>
              </div>
            </div>

            {/* API Key */}
            <div className="flex items-center gap-2 mb-3 p-2 bg-muted rounded-md">
              <span className="text-muted-foreground text-sm min-w-[60px]">API Key</span>
              <code className="text-foreground text-sm font-mono">
                {provider.api_key ? `${provider.api_key.slice(0, 8)}${'•'.repeat(20)}` : '(使用环境变量)'}
              </code>
            </div>

            {/* Models */}
            <div>
              <div className="text-foreground text-sm mb-2">模型</div>
              <div className="flex gap-1.5 flex-wrap mb-2">
                {(provider.models || []).map(m => (
                  <span
                    key={m.name}
                    className={`py-1 px-2.5 rounded-md border text-sm flex items-center gap-1.5 ${m.enabled ? 'bg-primary/10 text-primary border-primary/20' : 'bg-muted text-muted-foreground border-border'}`}
                  >
                    {m.name}
                    <button onClick={() => handleRemoveModel(provider.id, m.name)} className="bg-transparent border-none text-error cursor-pointer p-0 text-xs">✕</button>
                  </span>
                ))}
                {(!provider.models || provider.models.length === 0) && <span className="text-muted-foreground text-sm">暂无模型，请添加模型</span>}
              </div>
              <div className="flex gap-1.5">
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
                  className="flex-1 py-1.5 px-2.5 bg-muted border border-border rounded-md text-foreground text-sm focus:outline-none focus:border-primary placeholder:text-muted-foreground"
                />
                <button
                  onClick={() => handleAutoDetectModels(provider.id)}
                  className={btnSmPurple}
                >
                  🔍 自动获取
                </button>
              </div>
            </div>

            {/* Test result */}
            {testResult[provider.id] && (
              <div className={`mt-3 p-2 rounded-md text-sm ${testResult[provider.id].startsWith('✓') ? 'bg-success/10 text-success' : 'bg-error/10 text-error'}`}>
                {testResult[provider.id]}
              </div>
            )}
          </div>
        );
      })}

      {msg && (
        <div className={`text-sm text-center ${msg.includes('失败') || msg.includes('不能') ? 'text-error' : 'text-success'}`}>
          {msg}
        </div>
      )}
    </div>
  );
}
