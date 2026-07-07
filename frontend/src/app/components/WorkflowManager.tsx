'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiBase } from '@/lib/api';
import { useTheme } from '@/hooks/useTheme';

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
  { id: 'coordinator', label: '协调者' },
  { id: 'research_agent', label: '研究员' },
  { id: 'data_agent', label: '数据分析师' },
  { id: 'analyzer_agent', label: '分析师' },
  { id: 'modeler_agent', label: '建模师' },
  { id: 'algorithm_engineer_agent', label: '算法工程师' },
  { id: 'financial_analyst_agent', label: '金融分析师' },
  { id: 'solver_agent', label: '求解器' },
  { id: 'writer_agent', label: '写作专家' },
  { id: 'peer_review_agent', label: '同行评议' },
  { id: 'experimentation_agent', label: '实验设计专家' },
  { id: 'figure_agent', label: '科研绘图师' },
];

export default function WorkflowManager() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const { theme } = useTheme();
  const dark = theme === 'dark';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(apiBase() + '/workflows');
      if (res.ok) setWorkflows(await res.json());
    } catch {} finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div style={{ color: '#aaa', textAlign: 'center', padding: '2rem' }}>加载中...</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{
        background: dark ? '#1e293b' : 'rgba(255,255,255,0.05)',
        border: `1px solid ${dark ? '#334155' : 'rgba(255,255,255,0.1)'}`,
        borderRadius: 14, padding: '1.5rem'
      }}>
        <div style={{ marginBottom: '1rem' }}>
          <span style={{ fontSize: '1.1rem', color: dark ? '#f1f5f9' : '#fff', fontWeight: 600 }}>🔄 工作流</span>
          <div style={{ marginTop: '0.5rem', color: dark ? '#94a3b8' : '#aaa', fontSize: '0.8rem' }}>
            工作流已由模板自动绑定，此处仅展示各模板对应的 Agent 执行路径。
          </div>
        </div>

        {workflows.map(wf => (
          <div key={wf.name} style={{
            padding: '1rem', marginBottom: '0.8rem',
            background: dark ? 'rgba(59,130,246,0.08)' : 'rgba(52,152,219,0.05)',
            border: `1px solid ${dark ? '#475569' : 'rgba(255,255,255,0.08)'}`,
            borderRadius: 8
          }}>
            <div style={{ marginBottom: '0.5rem' }}>
              <span style={{ color: dark ? '#f1f5f9' : '#fff', fontWeight: 600 }}>{wf.name}</span>
              <span style={{
                marginLeft: '0.5rem', padding: '0.2rem 0.4rem', borderRadius: 4, fontSize: '0.7rem',
                background: dark ? '#1e3a5f' : 'rgba(52,152,219,0.15)',
                color: dark ? '#93c5fd' : '#3498db',
              }}>
                预定义
              </span>
            </div>
            <div style={{ color: dark ? '#94a3b8' : '#aaa', fontSize: '0.85rem', marginBottom: '0.5rem' }}>{wf.description}</div>
            <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
              {wf.steps.map((step, i) => (
                <span key={i} style={{
                  padding: '0.2rem 0.5rem',
                  background: dark ? 'rgba(30,41,59,0.8)' : 'rgba(0,0,0,0.2)',
                  borderRadius: 12, color: dark ? '#cbd5e1' : '#ddd', fontSize: '0.75rem',
                  border: `1px solid ${dark ? '#475569' : 'rgba(255,255,255,0.08)'}`,
                }}>
                  {i + 1}. {AGENTS.find(a => a.id === step.agent)?.label || step.agent}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
