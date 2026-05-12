'use client';

import { useState, useEffect, useCallback } from 'react';

interface WorkflowStep {
  agent: string;
  input: Record<string, string>;
}

interface Workflow {
  name: string;
  description: string;
  steps: WorkflowStep[];
  type: 'predefined' | 'custom';
  editable: boolean;
}

const AGENTS = [
  { id: 'research_agent', label: '研究员' },
  { id: 'analyzer_agent', label: '分析师' },
  { id: 'modeler_agent', label: '建模师' },
  { id: 'solver_agent', label: '求解器' },
  { id: 'writer_agent', label: '写作专家' },
];

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

export default function WorkflowManager() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');

  // Create/edit form
  const [showForm, setShowForm] = useState(false);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formSteps, setFormSteps] = useState<WorkflowStep[]>([{ agent: 'research_agent', input: { action: 'search' } }]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(apiBase() + '/workflows');
      if (res.ok) setWorkflows(await res.json());
    } catch {} finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const resetForm = () => {
    setFormName('');
    setFormDesc('');
    setFormSteps([{ agent: 'research_agent', input: { action: 'search' } }]);
    setEditingName(null);
  };

  const handleCreate = async () => {
    if (!formName) { setMsg('名称不能为空'); return; }
    try {
      const res = await fetch(apiBase() + '/workflows', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: formName, description: formDesc, steps: formSteps }),
      });
      const data = await res.json();
      if (data.success) { setMsg(`工作流 ${formName} 已创建`); setShowForm(false); resetForm(); load(); }
      else { setMsg(data.detail || '创建失败'); }
    } catch { setMsg('创建失败'); }
  };

  const handleUpdate = async () => {
    if (!editingName) return;
    try {
      const res = await fetch(apiBase() + '/workflows/' + editingName, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: editingName, description: formDesc, steps: formSteps }),
      });
      const data = await res.json();
      if (data.success) { setMsg(`工作流 ${editingName} 已更新`); setShowForm(false); resetForm(); load(); }
      else { setMsg(data.detail || '更新失败'); }
    } catch { setMsg('更新失败'); }
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`确定删除工作流 "${name}" 吗？`)) return;
    try {
      const res = await fetch(apiBase() + '/workflows/' + name, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) { setMsg(`已删除 ${name}`); load(); }
      else { setMsg(data.detail || '删除失败'); }
    } catch { setMsg('删除失败'); }
  };

  const startEdit = (wf: Workflow) => {
    setEditingName(wf.name);
    setFormName(wf.name);
    setFormDesc(wf.description);
    setFormSteps(wf.steps);
    setShowForm(true);
  };

  const addStep = () => {
    setFormSteps([...formSteps, { agent: 'research_agent', input: { action: 'search' } }]);
  };

  const removeStep = (idx: number) => {
    setFormSteps(formSteps.filter((_, i) => i !== idx));
  };

  const updateStep = (idx: number, field: 'agent' | 'input_key' | 'input_value', value: string) => {
    const steps = [...formSteps];
    if (field === 'agent') {
      steps[idx] = { ...steps[idx], agent: value };
    } else if (field === 'input_key') {
      const key = value;
      const oldVal = Object.values(steps[idx].input)[0] || '';
      steps[idx] = { ...steps[idx], input: { [key]: oldVal } };
    } else {
      const key = Object.keys(steps[idx].input)[0] || 'action';
      steps[idx] = { ...steps[idx], input: { [key]: value } };
    }
    setFormSteps(steps);
  };

  if (loading) return <div style={{ color: '#aaa', textAlign: 'center', padding: '2rem' }}>加载中...</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Workflow list */}
      <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <span style={{ fontSize: '1.1rem', color: '#fff', fontWeight: 600 }}>🔄 工作流管理</span>
          <button onClick={() => { resetForm(); setShowForm(true); }} style={{ padding: '0.4rem 0.8rem', background: 'rgba(46,204,113,0.15)', border: '1px solid rgba(46,204,113,0.3)', borderRadius: 6, color: '#2ecc71', fontSize: '0.78rem', cursor: 'pointer' }}>+ 创建自定义工作流</button>
        </div>

        {workflows.map(wf => (
          <div key={wf.name} style={{ padding: '1rem', marginBottom: '0.8rem', background: wf.type === 'predefined' ? 'rgba(52,152,219,0.05)' : 'rgba(46,204,113,0.05)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <div>
                <span style={{ color: '#fff', fontWeight: 600 }}>{wf.name}</span>
                <span style={{ marginLeft: '0.5rem', padding: '0.2rem 0.4rem', borderRadius: 4, fontSize: '0.7rem', background: wf.type === 'predefined' ? 'rgba(52,152,219,0.15)' : 'rgba(46,204,113,0.15)', color: wf.type === 'predefined' ? '#3498db' : '#2ecc71' }}>
                  {wf.type === 'predefined' ? '预定义' : '自定义'}
                </span>
              </div>
              {wf.editable && (
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button onClick={() => startEdit(wf)} style={{ padding: '0.3rem 0.6rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 6, color: '#3498db', fontSize: '0.75rem', cursor: 'pointer' }}>编辑</button>
                  <button onClick={() => handleDelete(wf.name)} style={{ padding: '0.3rem 0.6rem', background: 'rgba(231,76,60,0.15)', border: '1px solid rgba(231,76,60,0.3)', borderRadius: 6, color: '#e74c3c', fontSize: '0.75rem', cursor: 'pointer' }}>删除</button>
                </div>
              )}
            </div>
            <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '0.5rem' }}>{wf.description}</div>
            <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
              {wf.steps.map((step, i) => (
                <span key={i} style={{ padding: '0.2rem 0.5rem', background: 'rgba(0,0,0,0.2)', borderRadius: 12, color: '#ddd', fontSize: '0.75rem', border: '1px solid rgba(255,255,255,0.08)' }}>
                  {i + 1}. {AGENTS.find(a => a.id === step.agent)?.label || step.agent}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Create/Edit form */}
      {showForm && (
        <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
          <span style={{ fontSize: '1.1rem', color: '#fff', fontWeight: 600, display: 'block', marginBottom: '1rem' }}>
            {editingName ? `编辑工作流: ${editingName}` : '创建自定义工作流'}
          </span>

          <div style={{ marginBottom: '0.8rem' }}>
            <label style={{ color: '#ddd', fontSize: '0.85rem', display: 'block', marginBottom: '0.3rem' }}>名称</label>
            <input value={formName} onChange={e => setFormName(e.target.value)} disabled={!!editingName} placeholder="工作流名称" style={{ width: '100%', padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }} />
          </div>

          <div style={{ marginBottom: '0.8rem' }}>
            <label style={{ color: '#ddd', fontSize: '0.85rem', display: 'block', marginBottom: '0.3rem' }}>描述</label>
            <input value={formDesc} onChange={e => setFormDesc(e.target.value)} placeholder="工作流描述" style={{ width: '100%', padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }} />
          </div>

          <div style={{ marginBottom: '0.8rem' }}>
            <label style={{ color: '#ddd', fontSize: '0.85rem', display: 'block', marginBottom: '0.3rem' }}>步骤</label>
            {formSteps.map((step, idx) => (
              <div key={idx} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span style={{ color: '#888', fontSize: '0.8rem', minWidth: 20 }}>{idx + 1}.</span>
                <select value={step.agent} onChange={e => updateStep(idx, 'agent', e.target.value)} style={{ padding: '0.4rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 6, color: '#e0e0e0', fontSize: '0.85rem' }}>
                  {AGENTS.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
                </select>
                <input value={Object.keys(step.input)[0] || 'action'} onChange={e => updateStep(idx, 'input_key', e.target.value)} placeholder="参数名" style={{ width: 80, padding: '0.4rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 6, color: '#e0e0e0', fontSize: '0.85rem' }} />
                <input value={Object.values(step.input)[0] || ''} onChange={e => updateStep(idx, 'input_value', e.target.value)} placeholder="参数值" style={{ width: 120, padding: '0.4rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 6, color: '#e0e0e0', fontSize: '0.85rem' }} />
                {formSteps.length > 1 && (
                  <button onClick={() => removeStep(idx)} style={{ padding: '0.3rem 0.5rem', background: 'rgba(231,76,60,0.15)', border: '1px solid rgba(231,76,60,0.3)', borderRadius: 6, color: '#e74c3c', fontSize: '0.75rem', cursor: 'pointer' }}>✕</button>
                )}
              </div>
            ))}
            <button onClick={addStep} style={{ padding: '0.3rem 0.6rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 6, color: '#3498db', fontSize: '0.75rem', cursor: 'pointer' }}>+ 添加步骤</button>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button onClick={editingName ? handleUpdate : handleCreate} style={{ padding: '0.5rem 1rem', background: 'linear-gradient(135deg, #3498db, #2ecc71)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>
              {editingName ? '保存修改' : '创建工作流'}
            </button>
            <button onClick={() => { setShowForm(false); resetForm(); }} style={{ padding: '0.5rem 1rem', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#aaa', cursor: 'pointer' }}>取消</button>
          </div>
        </div>
      )}

      {msg && <div style={{ fontSize: '0.85rem', color: msg.includes('失败') || msg.includes('不能') ? '#e74c3c' : '#2ecc71', textAlign: 'center' }}>{msg}</div>}
    </div>
  );
}