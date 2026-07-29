'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiBase } from '@/lib/api';

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

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(apiBase() + '/workflows');
      if (res.ok) setWorkflows(await res.json());
    } catch {} finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="text-center text-muted-foreground py-8">加载中...</div>;

  return (
    <div className="flex flex-col gap-6">
      <div className="bg-card border border-border rounded-xl p-5">
        <div className="mb-4">
          <span className="text-base text-foreground font-semibold">🔄 工作流</span>
          <div className="mt-1 text-xs text-muted-foreground">
            工作流已由模板自动绑定，此处仅展示各模板对应的 Agent 执行路径。
          </div>
        </div>

        {workflows.map(wf => (
          <div key={wf.name} className="border border-border rounded-lg p-3 mb-3 last:mb-0">
            <div className="mb-2 flex items-center gap-2">
              <span className="text-foreground font-semibold">{wf.name}</span>
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-secondary text-secondary-foreground border border-border">
                预定义
              </span>
            </div>
            <div className="text-sm text-muted-foreground mb-2">{wf.description}</div>
            <div className="flex gap-1.5 flex-wrap">
              {wf.steps.map((step, i) => (
                <span key={i} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-secondary text-secondary-foreground border border-border">
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
