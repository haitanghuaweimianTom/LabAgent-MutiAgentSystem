'use client';

import { cn } from '@/lib/utils';

interface Stage {
  id: string;
  name: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  progress: number;
  detail?: string;
}

interface MemoryItem {
  key: string;
  label: string;
  content: string;
}

interface StageProgressProps {
  stages: Stage[];
  memoryPool?: MemoryItem[];
  currentStep?: string;
}

const STAGE_ICONS: Record<string, string> = {
  analysis: '🔍',
  modeling: '📐',
  solving: '⚙️',
  experiment: '🔬',
  writing: '📝',
};

const STATUS_CLASSES: Record<string, string> = {
  running: 'bg-[rgba(45,212,191,0.15)] border-[rgba(45,212,191,0.15)] text-[#3498db]',
  completed: 'bg-[rgba(74,222,128,0.15)] border-[rgba(74,222,128,0.15)] text-[#2ecc71]',
  failed: 'bg-[rgba(248,113,113,0.15)] border-[rgba(248,113,113,0.15)] text-[#e74c3c]',
  skipped: 'bg-[rgba(149,165,166,0.12)] border-[rgba(149,165,166,0.4)] text-[#95a5a6] line-through opacity-70',
};

export default function StageProgress({ stages, memoryPool, currentStep }: StageProgressProps) {
  const completedCount = stages.filter(s => s.status === 'completed').length;

  return (
    <div className="bg-[#1E293B] border border-[#334155] rounded-[14px] p-[1.2rem] mb-4">
      <div className="flex justify-between items-center mb-4">
        <span className="text-[1rem] text-[#F8FAFC] font-semibold">📊 五阶段流水线</span>
        <span className="text-[0.875rem] text-[#94A3B8]">
          {completedCount}/{stages.length} 阶段完成
          {currentStep && ` · 当前: ${currentStep}`}
        </span>
      </div>

      <div className="grid grid-cols-4 gap-2 relative max-md:grid-cols-1">
        {stages.map((stage, idx) => (
          <div key={stage.id} className="relative flex flex-col items-center">
            {idx > 0 && (
              <div className={cn(
                'absolute top-[18px] -left-1/2 w-full h-[2px] z-0',
                stage.status !== 'pending'
                  ? 'bg-gradient-to-r from-[#2ecc71] to-[#3498db]'
                  : 'bg-[#334155]'
              )} />
            )}

            <div className="w-full flex flex-col items-center gap-2">
              <div className={cn(
                'flex items-center gap-[0.4rem] py-[0.4rem] px-[0.8rem] rounded-[20px] text-[0.82rem] font-semibold border border-[#334155] bg-[#1E293B] text-[#94A3B8] z-[1] whitespace-nowrap',
                STATUS_CLASSES[stage.status]
              )}>
                <span className="text-[0.9375rem]">{STAGE_ICONS[stage.id] || '●'}</span>
                <span className="text-[0.875rem]">{stage.name}</span>
                {stage.status === 'running' && <span className="w-3 h-3 border-2 border-[rgba(45,212,191,0.15)] border-t-[#3498db] rounded-full animate-spin" />}
                {stage.status === 'completed' && <span className="text-[#2ecc71] font-bold">✓</span>}
                {stage.status === 'failed' && <span className="text-[#e74c3c] font-bold">✕</span>}
                {stage.status === 'skipped' && <span className="text-[#95a5a6] font-bold">⊘</span>}
              </div>

              {stage.status !== 'pending' && stage.status !== 'skipped' && (
                <div className="w-full p-[0.6rem] bg-black/20 rounded-[8px] text-center">
                  <div className="text-[0.875rem] text-[#94A3B8] leading-normal">{stage.description}</div>
                  {stage.progress > 0 && stage.status !== 'completed' && (
                    <div className="h-[3px] bg-[#334155] rounded-[2px] mt-[0.4rem] overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-[#3498db] to-[#2ecc71] rounded-[2px] transition-[width] duration-500 ease-in-out" style={{ width: `${stage.progress}%` }} />
                    </div>
                  )}
                  {stage.detail && <div className="text-[0.72rem] text-[#64748B] mt-[0.3rem]">{stage.detail}</div>}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {memoryPool && memoryPool.length > 0 && (
        <div className="mt-4 pt-4 border-t border-[#334155]">
          <div className="text-[0.9375rem] text-[#f39c12] font-semibold mb-2">🧠 显式记忆池</div>
          <div className="flex flex-wrap gap-[0.4rem]">
            {memoryPool.map(m => (
              <div key={m.key} className="flex items-center gap-[0.3rem] py-[0.3rem] px-[0.6rem] bg-[#1E293B] border border-[#334155] rounded-[6px]">
                <span className="text-[0.72rem] text-[#94A3B8] font-semibold whitespace-nowrap">{m.label}</span>
                <span className="text-[0.72rem] text-[#64748B] max-w-[200px] overflow-hidden text-ellipsis whitespace-nowrap">{m.content}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
