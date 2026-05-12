'use client';

import { useState, useEffect, useCallback } from 'react';

interface AgentInfo {
  name: string;
  label: string;
  description: string;
  model: string;
}

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

const AGENT_COLORS: Record<string, string> = {
  coordinator: '#e74c3c',
  research_agent: '#3498db',
  data_agent: '#9b59b6',
  analyzer_agent: '#f39c12',
  modeler_agent: '#27ae60',
  solver_agent: '#e67e22',
  writer_agent: '#1abc9c',
};

const AGENT_ICONS: Record<string, string> = {
  coordinator: '🎯',
  research_agent: '🔍',
  data_agent: '📊',
  analyzer_agent: '🧠',
  modeler_agent: '📐',
  solver_agent: '💻',
  writer_agent: '📝',
};

export default function AgentManager() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');
  const [editingAgent, setEditingAgent] = useState<string | null>(null);
  const [editModel, setEditModel] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(apiBase() + '/agents');
      if (res.ok) setAgents(await res.json());
    } catch {} finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleUpdateModel = async (agentName: string) => {
    if (!editModel.trim()) { setMsg('模型名称不能为空'); return; }
    try {
      const res = await fetch(apiBase() + '/agents/' + agentName + '/model', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: editModel.trim() }),
      });
      const data = await res.json();
      if (data.model) { setMsg(`${agentName} 模型已更新为 ${data.model}`); setEditingAgent(null); load(); }
      else { setMsg('更新失败'); }
    } catch { setMsg('更新失败'); }
  };

  if (loading) return <div style={{ color: '#aaa', textAlign: 'center', padding: '2rem' }}>加载中...</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
        <span style={{ fontSize: '1.1rem', color: '#fff', fontWeight: 600, display: 'block', marginBottom: '1rem' }}>🤖 Agent 团队管理</span>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
          {agents.map(agent => (
            <div key={agent.name} style={{ background: 'rgba(0,0,0,0.15)', border: `1px solid ${AGENT_COLORS[agent.name] || '#666'}33`, borderRadius: 10, padding: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <span style={{ fontSize: '1.2rem' }}>{AGENT_ICONS[agent.name] || '🤖'}</span>
                <span style={{ color: '#fff', fontWeight: 600, fontSize: '1rem' }}>{agent.label}</span>
                <span style={{ color: '#888', fontSize: '0.8rem' }}>{agent.name}</span>
              </div>
              <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '0.8rem' }}>{agent.description}</div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ color: '#888', fontSize: '0.8rem' }}>模型:</span>
                {editingAgent === agent.name ? (
                  <>
                    <input
                      value={editModel}
                      onChange={e => setEditModel(e.target.value)}
                      placeholder={agent.model}
                      style={{ flex: 1, padding: '0.4rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 6, color: '#e0e0e0', fontSize: '0.85rem' }}
                      onKeyDown={e => { if (e.key === 'Enter') handleUpdateModel(agent.name); }}
                    />
                    <button onClick={() => handleUpdateModel(agent.name)} style={{ padding: '0.3rem 0.6rem', background: 'rgba(46,204,113,0.15)', border: '1px solid rgba(46,204,113,0.3)', borderRadius: 6, color: '#2ecc71', fontSize: '0.75rem', cursor: 'pointer' }}>确认</button>
                    <button onClick={() => setEditingAgent(null)} style={{ padding: '0.3rem 0.6rem', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, color: '#aaa', fontSize: '0.75rem', cursor: 'pointer' }}>取消</button>
                  </>
                ) : (
                  <>
                    <code style={{ color: `${AGENT_COLORS[agent.name] || '#ddd'}`, fontSize: '0.85rem', background: 'rgba(0,0,0,0.2)', padding: '0.2rem 0.4rem', borderRadius: 4 }}>{agent.model}</code>
                    <button onClick={() => { setEditingAgent(agent.name); setEditModel(agent.model); }} style={{ padding: '0.3rem 0.5rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 6, color: '#3498db', fontSize: '0.7rem', cursor: 'pointer' }}>修改</button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {msg && <div style={{ fontSize: '0.85rem', color: msg.includes('失败') || msg.includes('不能') ? '#e74c3c' : '#2ecc71', textAlign: 'center' }}>{msg}</div>}
    </div>
  );
}