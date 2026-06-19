'use client';

import { useState, useEffect, useCallback } from 'react';

interface ProviderModel {
  name: string;
  display_name?: string;
  enabled?: boolean;
}

interface CustomProvider {
  id: string;
  name: string;
  type: string;
  api_key: string;
  api_host: string;
  models: ProviderModel[];
  meta?: { api_format?: string; auth_field?: string };
  icon?: string;
  icon_color?: string;
  category?: string;
  enabled?: boolean;
}

interface AgentInfo {
  name: string;
  label: string;
  description: string;
  model: string;
  provider_id: string;
  provider_model: string;
  provider_name: string;
}

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

const AGENT_COLORS: Record<string, string> = {
  coordinator: '#e74c3c',
  research_agent: '#3498db',
  data_agent: '#9b59b6',
  analyzer_agent: '#f39c12',
  modeler_agent: '#27ae60',
  algorithm_engineer_agent: '#16a085',
  financial_analyst_agent: '#d4ac0d',
  solver_agent: '#e67e22',
  writer_agent: '#1abc9c',
  peer_review_agent: '#8e44ad',
  experimentation_agent: '#2c3e50',
  figure_agent: '#e84393',
};

const AGENT_ICONS: Record<string, string> = {
  coordinator: '🎯',
  research_agent: '🔍',
  data_agent: '📊',
  analyzer_agent: '🧠',
  modeler_agent: '📐',
  algorithm_engineer_agent: '⚙️',
  financial_analyst_agent: '💹',
  solver_agent: '💻',
  writer_agent: '📝',
  peer_review_agent: '👁️',
  experimentation_agent: '🔬',
  figure_agent: '📈',
};

export default function AgentManager() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [providers, setProviders] = useState<CustomProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');

  // Per-agent editing state
  const [editingAgent, setEditingAgent] = useState<string | null>(null);
  const [editProviderId, setEditProviderId] = useState('');
  const [editModelName, setEditModelName] = useState('');

  // Per-agent test state
  const [testingAgent, setTestingAgent] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});

  // Per-model test state (test individual model within a provider)
  const [testingModel, setTestingModel] = useState<string | null>(null);
  const [modelTestResults, setModelTestResults] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [agentsRes, providersRes] = await Promise.all([
        fetch(apiBase() + '/agents', { cache: 'no-store' }),
        fetch(apiBase() + '/providers/', { cache: 'no-store' }),
      ]);
      if (agentsRes.ok) {
        const data = await agentsRes.json();
        setAgents(data);
      }
      if (providersRes.ok) {
        const data = await providersRes.json();
        setProviders(data.custom_providers || []);
      }
    } catch {} finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (agentName: string) => {
    if (!editProviderId || !editModelName) { setMsg('请选择 Provider 和模型'); return; }
    try {
      const res = await fetch(apiBase() + '/agents/' + agentName + '/model', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: editModelName,
          provider_id: editProviderId,
        }),
      });
      const data = await res.json();
      if (data.model) {
        setMsg(`✓ ${AGENT_ICONS[agentName] || ''} ${agentName} 已保存: ${data.provider_id}/${data.model}`);
        setEditingAgent(null);
        load(); // reload to reflect persisted changes
      } else {
        setMsg('✗ 保存失败: ' + (data.detail || ''));
      }
    } catch { setMsg('✗ 保存失败'); }
  };

  // Test the full agent model config (provider + model combination)
  const handleTestAgentModel = async (agentName: string, providerId: string, modelName: string) => {
    if (!providerId) { setMsg('请先配置 Provider'); return; }
    setTestingAgent(agentName);
    setTestResults(prev => ({ ...prev, [agentName]: '测试中...' }));
    try {
      const res = await fetch(apiBase() + '/agents/' + agentName + '/test-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider_id: providerId, model: modelName }),
      });
      const data = await res.json();
      if (data.success) {
        setTestResults(prev => ({ ...prev, [agentName]: `✓ ${modelName} 可用 (${data.latency_ms}ms): ${data.response}` }));
      } else {
        setTestResults(prev => ({ ...prev, [agentName]: `✗ ${modelName}: ${data.error || '连接失败'} ${data.detail ? '(' + data.detail.slice(0, 100) + ')' : ''}` }));
      }
    } catch {
      setTestResults(prev => ({ ...prev, [agentName]: '✗ 连接失败' }));
    } finally { setTestingAgent(null); }
  };

  // Test an individual model within a provider (before saving)
  const handleTestIndividualModel = async (providerId: string, modelName: string) => {
    const key = `${providerId}/${modelName}`;
    setTestingModel(key);
    setModelTestResults(prev => ({ ...prev, [key]: '测试中...' }));
    try {
      const res = await fetch(apiBase() + '/providers/' + providerId + '/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: modelName }),
      });
      const data = await res.json();
      if (data.success) {
        setModelTestResults(prev => ({ ...prev, [key]: `✓ (${data.latency_ms}ms)` }));
      } else {
        setModelTestResults(prev => ({ ...prev, [key]: `✗ ${data.error || ''}` }));
      }
    } catch {
      setModelTestResults(prev => ({ ...prev, [key]: '✗ 连接失败' }));
    } finally { setTestingModel(null); }
  };

  const startEdit = (agent: AgentInfo) => {
    setEditingAgent(agent.name);
    setEditProviderId(agent.provider_id || '');
    setEditModelName(agent.provider_model || agent.model || '');
  };

  const getProvider = (providerId: string) => providers.find(p => p.id === providerId);

  if (loading) return <div style={{ color: '#aaa', textAlign: 'center', padding: '2rem' }}>加载中...</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
        <span style={{ fontSize: '1.1rem', color: '#fff', fontWeight: 600 }}>🤖 Agent 团队模型配置</span>
        <div style={{ color: '#888', fontSize: '0.8rem', marginTop: '0.3rem' }}>
          为每个 Agent 从可用 Provider 中选择模型，支持单独测试每个模型是否可用
        </div>
        {providers.length === 0 && (
          <div style={{ color: '#e74c3c', fontSize: '0.85rem', marginTop: '0.5rem' }}>
            ⚠ 尚未配置任何 Provider，请先到「设置 → Provider 管理」添加
          </div>
        )}
      </div>

      {/* Agent grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1rem' }}>
        {agents.map(agent => {
          const color = AGENT_COLORS[agent.name] || '#666';
          const icon = AGENT_ICONS[agent.name] || '🤖';
          const isEditing = editingAgent === agent.name;
          const currentProvider = isEditing ? getProvider(editProviderId) : getProvider(agent.provider_id);
          const currentModelName = isEditing ? editModelName : (agent.provider_model || agent.model);
          const providerModels = currentProvider?.models?.filter(m => m.enabled) || [];

          return (
            <div key={agent.name} style={{ background: 'rgba(0,0,0,0.15)', border: `1px solid ${color}33`, borderRadius: 10, padding: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.6rem' }}>
                <span style={{ fontSize: '1.3rem' }}>{icon}</span>
                <span style={{ color: '#fff', fontWeight: 600, fontSize: '1rem' }}>{agent.label}</span>
                <span style={{ color: '#888', fontSize: '0.75rem' }}>{agent.name}</span>
              </div>
              <div style={{ color: '#aaa', fontSize: '0.82rem', marginBottom: '0.8rem' }}>{agent.description}</div>

              {isEditing ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                  {/* Provider selector */}
                  <div>
                    <div style={{ color: '#888', fontSize: '0.78rem', marginBottom: '0.3rem' }}>Provider</div>
                    <select
                      value={editProviderId}
                      onChange={e => {
                        const newProvId = e.target.value;
                        const newProv = getProvider(newProvId);
                        const firstModel = newProv?.models?.find(m => m.enabled)?.name || newProv?.models?.[0]?.name || '';
                        setEditProviderId(newProvId);
                        setEditModelName(firstModel);
                        setModelTestResults({}); // clear model test results on provider change
                      }}
                      style={{ width: '100%', padding: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 6, color: '#e0e0e0', fontSize: '0.85rem' }}
                    >
                      <option value="">选择 Provider</option>
                      {providers.map(p => (
                        <option key={p.id} value={p.id}>
                          {p.name} ({p.api_host})
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Model selector */}
                  <div>
                    <div style={{ color: '#888', fontSize: '0.78rem', marginBottom: '0.3rem' }}>模型</div>
                    {providerModels.length > 0 ? (
                      <select
                        value={editModelName}
                        onChange={e => setEditModelName(e.target.value)}
                        style={{ width: '100%', padding: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 6, color: '#e0e0e0', fontSize: '0.85rem' }}
                      >
                        {providerModels.map(m => (
                          <option key={m.name} value={m.name}>{m.display_name || m.name}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        value={editModelName}
                        onChange={e => setEditModelName(e.target.value)}
                        placeholder="输入模型名称"
                        style={{ width: '100%', padding: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 6, color: '#e0e0e0', fontSize: '0.85rem' }}
                      />
                    )}
                  </div>

                  {/* Test individual model button */}
                  {editProviderId && editModelName && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <button
                        onClick={() => handleTestIndividualModel(editProviderId, editModelName)}
                        disabled={testingModel === `${editProviderId}/${editModelName}`}
                        style={{ padding: '0.4rem 0.6rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 6, color: '#3498db', fontSize: '0.75rem', cursor: 'pointer' }}
                      >
                        {testingModel === `${editProviderId}/${editModelName}` ? '测试中...' : '🧪 测试此模型'}
                      </button>
                      {modelTestResults[`${editProviderId}/${editModelName}`] && (
                        <span style={{ fontSize: '0.8rem', color: modelTestResults[`${editProviderId}/${editModelName}`].startsWith('✓') ? '#2ecc71' : '#e74c3c' }}>
                          {modelTestResults[`${editProviderId}/${editModelName}`]}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Actions */}
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button onClick={() => handleSave(agent.name)} style={{ padding: '0.4rem 0.8rem', background: 'rgba(46,204,113,0.15)', border: '1px solid rgba(46,204,113,0.3)', borderRadius: 6, color: '#2ecc71', fontSize: '0.78rem', cursor: 'pointer', fontWeight: 600 }}>
                      💾 保存
                    </button>
                    <button onClick={() => setEditingAgent(null)} style={{ padding: '0.4rem 0.8rem', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, color: '#aaa', fontSize: '0.78rem', cursor: 'pointer' }}>
                      取消
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  {/* Current config display */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    <span style={{ color: '#888', fontSize: '0.78rem' }}>当前:</span>
                    {agent.provider_id ? (
                      <code style={{ color: color, fontSize: '0.82rem', background: 'rgba(0,0,0,0.2)', padding: '0.2rem 0.4rem', borderRadius: 4 }}>
                        {agent.provider_name}/{currentModelName}
                      </code>
                    ) : (
                      <code style={{ color: '#888', fontSize: '0.82rem' }}>{agent.model}</code>
                    )}
                    <button onClick={() => startEdit(agent)} style={{ padding: '0.3rem 0.5rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 6, color: '#3498db', fontSize: '0.7rem', cursor: 'pointer' }}>
                      修改
                    </button>
                  </div>

                  {/* Test saved config */}
                  {agent.provider_id && currentModelName && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <button
                        onClick={() => handleTestAgentModel(agent.name, agent.provider_id, currentModelName)}
                        disabled={testingAgent === agent.name}
                        style={{ padding: '0.3rem 0.5rem', background: 'rgba(155,89,182,0.15)', border: '1px solid rgba(155,89,182,0.3)', borderRadius: 6, color: '#9b59b6', fontSize: '0.7rem', cursor: 'pointer' }}
                      >
                        {testingAgent === agent.name ? '测试中...' : '🧪 测试当前模型'}
                      </button>
                      {testResults[agent.name] && (
                        <span style={{ fontSize: '0.8rem', color: testResults[agent.name].startsWith('✓') ? '#2ecc71' : '#e74c3c' }}>
                          {testResults[agent.name]}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {msg && <div style={{ fontSize: '0.85rem', color: msg.startsWith('✗') ? '#e74c3c' : '#2ecc71', textAlign: 'center' }}>{msg}</div>}
    </div>
  );
}