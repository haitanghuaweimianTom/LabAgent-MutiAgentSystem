'use client';

import { useState, useEffect, useCallback } from 'react';
import { cn } from '@/lib/utils';
import TaskDetail from './TaskDetail';
import { apiBase } from '@/lib/api';
import { nodeLabel } from '@/lib/constants';

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
  completed: 'bg-success/15 text-success',
  running: 'bg-primary/10 text-primary',
  phase1: 'bg-primary/10 text-primary',
  phase2: 'bg-primary/10 text-primary',
  failed: 'bg-error/15 text-error',
  cancelled: 'bg-warning/15 text-warning',
  paused: 'bg-muted text-muted-foreground',
  unknown: 'bg-muted text-muted-foreground',
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
      'text-xs py-0.5 px-4 rounded-lg font-semibold whitespace-nowrap',
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
      const res = await fetch(apiBase() + '/tasks');
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
    <div data-design-id="history:root" className="grid grid-cols-[320px_1fr] gap-4 min-h-[600px] max-md:grid-cols-1 mx-auto w-full max-w-[1320px]">
      <div data-design-id="history:card-list" className="bg-card border border-border rounded-xl px-6 py-4 overflow-y-auto max-h-[700px]">
        <div className="flex justify-between items-center mb-4">
          <span data-design-id="history:title" className="text-lg text-foreground font-semibold">📋 历史任务</span>
          <div data-design-id="history:row-actions" className="flex gap-3 items-center">
            <button data-design-id="history:btn-refresh" className="inline-flex items-center justify-center gap-3 min-h-[40px] py-2 px-8 bg-primary/10 text-primary border border-primary/20 rounded-lg text-sm cursor-pointer transition-colors hover:bg-primary/20 disabled:opacity-50 disabled:cursor-not-allowed shrink-0" onClick={loadTaskList} disabled={loading}>
              {loading ? '加载中...' : '🔄 刷新'}
            </button>
            <button
              data-design-id="history:btn-selectall"
              className="inline-flex items-center justify-center gap-3 min-h-[40px] py-2 px-8 bg-primary/10 text-primary border border-primary/20 rounded-lg text-sm cursor-pointer transition-colors hover:bg-primary/20 shrink-0"
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
              <button data-design-id="history:btn-batchdelete" className="inline-flex items-center justify-center gap-3 min-h-[36px] py-1.5 px-6 bg-error/10 text-error border border-error/20 rounded-md text-sm cursor-pointer transition-colors hover:bg-error/15 disabled:opacity-50 disabled:cursor-not-allowed shrink-0" onClick={handleBatchDelete} disabled={batchDeleting}>
                🗑️ 批量删除({selectedIds.size})
              </button>
            )}
          </div>
        </div>

        {loading && taskList.length === 0 && <div className="text-center p-8 text-muted-foreground text-sm">加载中...</div>}
        {!loading && taskList.length === 0 && <div className="text-center p-8 text-muted-foreground text-sm">暂无历史任务</div>}

        <div className="flex flex-col gap-3">
          {taskList.map(task => (
            <div
              key={task.task_id}
              className={cn(
                'flex items-start gap-3 px-5 py-3 rounded-lg border border-border bg-muted cursor-pointer transition-colors duration-150 hover:bg-muted/60 hover:border-foreground/20',
                detailTaskId === task.task_id && '!bg-primary/10 !border-primary/30'
              )}
              onClick={() => setDetailTaskId(task.task_id)}
            >
              <div className="pt-0.5">
                <input
                  type="checkbox"
                  checked={selectedIds.has(task.task_id)}
                  onChange={() => toggleSelection(task.task_id)}
                  onClick={e => e.stopPropagation()}
                  className="w-4 h-4 accent-primary cursor-pointer"
                />
              </div>
              <div className="flex-1">
                <div className="flex justify-between items-center mb-1.5">
                  <StatusBadge status={task.status} />
                  <span className="text-xs text-muted-foreground">{formatTime(task.created_at)}</span>
                </div>
                <div className="text-sm text-muted-foreground leading-normal display-[-webkit-box] [-webkit-line-clamp:2] [-webkit-box-orient:vertical] overflow-hidden mb-1.5">
                  {task.problem_preview || '（无题目描述）'}
                </div>
                <div className="flex gap-3 items-center text-xs text-muted-foreground">
                  {task.template && <span>📄 {task.template}</span>}
                  {task.workflow_type && <span>⚙️ {task.workflow_type}</span>}
                  {task.current_step && <span>📍 {nodeLabel(task.current_step)}</span>}
                  {task.total_steps > 0 && <span>📊 {task.total_steps} 步骤</span>}
                  <button className="ml-auto bg-transparent border-none cursor-pointer text-sm opacity-30 transition-opacity duration-200 p-0.5 hover:opacity-100" onClick={e => { e.stopPropagation(); handleDeleteOne(task.task_id); }} title="删除">
                    🗑️
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div data-design-id="history:card-detail" className="bg-card border border-border rounded-xl px-6 py-4 overflow-hidden flex flex-col min-h-[400px]">
        {detailTaskId ? (
          <TaskDetail
            taskId={detailTaskId}
            onDelete={() => handleDeleteOne(detailTaskId)}
            onRerun={(newTaskId) => { loadTaskList(); setDetailTaskId(newTaskId); }}
          />
        ) : (
          <div className="text-center p-8 text-muted-foreground text-sm">👈 点击左侧任务查看详情</div>
        )}
      </div>
    </div>
  );
}
