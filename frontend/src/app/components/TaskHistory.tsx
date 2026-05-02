'use client';

import { useState, useEffect, useCallback } from 'react';
import styles from './TaskHistory.module.css';
import TaskDetail from './TaskDetail';

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
}

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: styles.statusCompleted,
    running: styles.statusRunning,
    phase1: styles.statusRunning,
    phase2: styles.statusRunning,
    failed: styles.statusFailed,
    cancelled: styles.statusCancelled,
    paused: styles.statusPaused,
    unknown: styles.statusUnknown,
  };
  const labels: Record<string, string> = {
    completed: '✅ 已完成',
    running: '🔄 进行中',
    phase1: '🔄 阶段1',
    phase2: '🔄 阶段2',
    failed: '❌ 失败',
    cancelled: '⚠️ 已取消',
    paused: '⏸ 已暂停',
    unknown: '❓ 未知',
  };
  return (
    <span className={`${styles.statusBadge} ${map[status] || styles.statusUnknown}`}>
      {labels[status] || status}
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
    <div className={styles.container}>
      <div className={styles.listPanel}>
        <div className={styles.listHeader}>
          <span className={styles.title}>📋 历史任务</span>
          <div className={styles.headerActions}>
            {selectedIds.size > 0 && (
              <button className={styles.batchDeleteBtn} onClick={handleBatchDelete} disabled={batchDeleting}>
                🗑️ 批量删除({selectedIds.size})
              </button>
            )}
            <button className={styles.refreshBtn} onClick={loadTaskList} disabled={loading}>
              {loading ? '加载中...' : '🔄 刷新'}
            </button>
          </div>
        </div>

        {loading && taskList.length === 0 && <div className={styles.empty}>加载中...</div>}
        {!loading && taskList.length === 0 && <div className={styles.empty}>暂无历史任务</div>}

        <div className={styles.taskList}>
          {taskList.map(task => (
            <div
              key={task.task_id}
              className={`${styles.taskItem} ${detailTaskId === task.task_id ? styles.taskItemActive : ''}`}
              onClick={() => setDetailTaskId(task.task_id)}
            >
              <div className={styles.taskCheck}>
                <input
                  type="checkbox"
                  checked={selectedIds.has(task.task_id)}
                  onChange={() => toggleSelection(task.task_id)}
                  onClick={e => e.stopPropagation()}
                />
              </div>
              <div className={styles.taskBody}>
                <div className={styles.taskTop}>
                  <StatusBadge status={task.status} />
                  <span className={styles.taskTime}>{formatTime(task.created_at)}</span>
                </div>
                <div className={styles.taskPreview}>{task.problem_preview || '（无题目描述）'}</div>
                <div className={styles.taskMeta}>
                  {task.current_step && <span>📍 {task.current_step}</span>}
                  {task.total_steps > 0 && <span>📊 {task.total_steps} 步骤</span>}
                  <button className={styles.deleteOneBtn} onClick={e => { e.stopPropagation(); handleDeleteOne(task.task_id); }} title="删除">
                    🗑️
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className={styles.detailPanel}>
        {detailTaskId ? (
          <TaskDetail taskId={detailTaskId} onDelete={() => handleDeleteOne(detailTaskId)} />
        ) : (
          <div className={styles.empty}>👈 点击左侧任务查看详情</div>
        )}
      </div>
    </div>
  );
}
