'use client';

import { useState, useEffect, useCallback } from 'react';
import { cn } from '@/lib/utils';
import TaskDetail from './TaskDetail';
import { apiBase } from '@/lib/api';

interface TaskInfo {
  task_id: string;
  problem_text: string;
  problem_preview: string;
  status: string;
  created_at: string;
  completed_at?: string;
  error?: string;
  total_steps: number;
  progress: number;
  current_step: string;
  template?: string;
  workflow_type?: string;
}

const STATUS_BADGE_CLASSES: Record<string, string> = {
  completed: 'bg-[rgba(74,222,128,0.15)] text-[#2ecc71]',
  running: 'bg-[rgba(45,212,191,0.15)] text-[#3498db]',
  phase1: 'bg-[rgba(45,212,191,0.15)] text-[#3498db]',
  phase2: 'bg-[rgba(45,212,191,0.15)] text-[#3498db]',
  failed: 'bg-[rgba(248,113,113,0.15)] text-[#e74c3c]',
  cancelled: 'bg-[rgba(243,156,18,0.15)] text-[#f39c12]',
  paused: 'bg-[rgba(155,89,182,0.15)] text-[#bb8fce]',
  unknown: 'bg-[rgba(150,150,150,0.1)] text-[#94A3B8]',
};

const STATUS_LABELS: Record<string, string> = {
  completed: '✅ 已完成',
  running: '🔄 进行中',
  phase1: '🔄 阶段1',
  phase2: '🔄 阶段2',
  failed: '❌ 失败',
  cancelled: '⚠️ 已取消',
  paused: '⏸ 已暂停',
  unknown: '❓ 未知',
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={cn(
      'text-[0.72rem] py-[0.15rem] px-2 rounded-[10px] font-semibold whitespace-nowrap',
      STATUS_BADGE_CLASSES[status] || STATUS_BADGE_CLASSES.unknown
    )}>
      {STATUS_LABELS[status] || status}
    </span>
  );
}

function formatTime(iso: string) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString('zh-CN', { hour12: false }); } catch { return iso; }
}

export default function TaskHistory() {
  const [taskList, setTaskList] = useState<TaskInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailTaskId, setDetailTaskId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);

  const loadTaskList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(apiBase() + '/tasks/');
      if (res.ok) {
        const data = await res.json();
        setTaskList(data);
      }
    } catch {} finally { setLoading(false); }
  }, []);

  useEffect(() => { loadTaskList(); }, [loadTaskList]);

  const toggleSelection = (tid: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(tid)) next.delete(tid); else next.add(tid);
      return next;
    });
  };

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`确定删除选中的 ${selectedIds.size} 个任务吗？`)) return;
    setBatchDeleting(true);
    try {
      const res = await fetch(apiBase() + '/tasks/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_ids: Array.from(selectedIds) }),
      });
      const data = await res.json();
      alert(`已删除 ${data.deleted_count} 个任务`);
      setSelectedIds(new Set());
      setDetailTaskId(null);
      loadTaskList();
    } catch {} finally { setBatchDeleting(false); }
  };

  const handleDeleteOne = async (tid: string) => {
    if (!confirm(`确定删除任务 "${tid}" 吗？`)) return;
    try {
      await fetch(apiBase() + '/tasks/' + tid, { method: 'DELETE' });
      if (detailTaskId === tid) setDetailTaskId(null);
      loadTaskList();
    } catch {}
  };

  return (
    <div className="grid grid-cols-[320px_1fr] gap-4 min-h-[600px] max-md:grid-cols-1">
      <div className="bg-[#1E293B] border border-[#334155] rounded-[14px] p-4 overflow-y-auto max-h-[700px]">
        <div className="flex justify-between items-center mb-4">
          <span className="text-[1rem] text-[#F8FAFC] font-semibold">📋 历史任务</span>
          <div className="flex gap-2 items-center">
            <button className="py-[0.3rem] px-[0.8rem] bg-[#334155] border border-[#334155] rounded-[6px] text-[#94A3B8] text-[0.78rem] cursor-pointer transition-all duration-200 hover:bg-[#334155] disabled:opacity-40 disabled:cursor-not-allowed" onClick={loadTaskList} disabled={loading}>
              {loading ? '加载中...' : '🔄 刷新'}
            </button>
            <button
              className="py-[0.35rem] px-[0.9rem] bg-[rgba(45,212,191,0.15)] border border-[rgba(45,212,191,0.15)] rounded-[8px] text-[#3498db] text-[0.78rem] cursor-pointer transition-all duration-200 hover:bg-[rgba(45,212,191,0.15)]"
              onClick={() => {
                if (selectedIds.size === taskList.length) {
                  setSelectedIds(new Set());
                } else {
                  setSelectedIds(new Set(taskList.map(t => t.task_id)));
                }
              }}
            >
              {selectedIds.size === taskList.length && taskList.length > 0 ? '☑️ 取消全选' : '⬜ 全选'}
            </button>
            {selectedIds.size > 0 && (
              <button className="py-[0.35rem] px-[0.9rem] bg-[rgba(248,113,113,0.15)] border border-[rgba(248,113,113,0.15)] rounded-[8px] text-[#e74c3c] text-[0.82rem] cursor-pointer transition-all duration-200 hover:bg-[rgba(248,113,113,0.15)] disabled:opacity-50 disabled:cursor-not-allowed" onClick={handleBatchDelete} disabled={batchDeleting}>
                🗑️ 批量删除({selectedIds.size})
              </button>
            )}
          </div>
        </div>

        {loading && taskList.length === 0 && <div className="text-center p-8 text-[#475569] text-[0.9375rem]">加载中...</div>}
        {!loading && taskList.length === 0 && <div className="text-center p-8 text-[#475569] text-[0.9375rem]">暂无历史任务</div>}

        <div className="flex flex-col gap-2">
          {taskList.map(task => (
            <div
              key={task.task_id}
              className={cn(
                'flex items-start gap-2 p-[0.7rem] rounded-[10px] border border-[#334155] bg-black/20 cursor-pointer transition-all duration-200 hover:bg-[#334155] hover:border-[#475569]',
                detailTaskId === task.task_id && '!bg-[rgba(45,212,191,0.15)] !border-[rgba(45,212,191,0.15)]'
              )}
              onClick={() => setDetailTaskId(task.task_id)}
            >
              <div className="pt-[0.1rem]">
                <input
                  type="checkbox"
                  checked={selectedIds.has(task.task_id)}
                  onChange={() => toggleSelection(task.task_id)}
                  onClick={e => e.stopPropagation()}
                  className="w-4 h-4 accent-[#3498db] cursor-pointer"
                />
              </div>
              <div className="flex-1">
                <div className="flex justify-between items-center mb-[0.3rem]">
                  <StatusBadge status={task.status} />
                  <span className="text-[0.72rem] text-[#475569]">{formatTime(task.created_at)}</span>
                </div>
                <div className="text-[0.875rem] text-[#94A3B8] leading-normal display-[-webkit-box] [-webkit-line-clamp:2] [-webkit-box-orient:vertical] overflow-hidden mb-[0.3rem]">
                  {task.problem_preview || '（无题目描述）'}
                </div>
                <div className="flex gap-2 items-center text-[0.72rem] text-[#64748B]">
                  {task.template && <span>📄 {task.template}</span>}
                  {task.workflow_type && <span>⚙️ {task.workflow_type}</span>}
                  {task.current_step && <span>📍 {task.current_step}</span>}
                  {task.total_steps > 0 && <span>📊 {task.total_steps} 步骤</span>}
                  <button className="ml-auto bg-transparent border-none cursor-pointer text-[0.875rem] opacity-30 transition-opacity duration-200 p-[0.2rem] hover:opacity-100" onClick={e => { e.stopPropagation(); handleDeleteOne(task.task_id); }} title="删除">
                    🗑️
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-[#1E293B] border border-[#334155] rounded-[14px] p-4 overflow-hidden flex flex-col min-h-[400px]">
        {detailTaskId ? (
          <TaskDetail
            taskId={detailTaskId}
            onDelete={() => handleDeleteOne(detailTaskId)}
            onRerun={(newTaskId) => { loadTaskList(); setDetailTaskId(newTaskId); }}
          />
        ) : (
          <div className="text-center p-8 text-[#475569] text-[0.9375rem]">👈 点击左侧任务查看详情</div>
        )}
      </div>
    </div>
  );
}
