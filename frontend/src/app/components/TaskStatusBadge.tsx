'use client';

/**
 * 任务状态徽章（Phase 6）。
 * 与 [useTaskState.ts](../hooks/useTaskState.ts) 的状态枚举对齐。
 */

import React from 'react';
import type { TaskStateName } from '../hooks/useTaskState';

interface TaskStatusBadgeProps {
  state: TaskStateName;
  progressPercentage?: number;
  compact?: boolean;
}

const STATE_META: Record<TaskStateName, { label: string; color: string; icon: string }> = {
  idle:              { label: '待启动',  color: '#9ca3af', icon: '○' },
  phase1_running:    { label: '分析中',  color: '#3b82f6', icon: '▶' },
  phase1_reviewing:  { label: '待用户确认', color: '#f59e0b', icon: '⏸' },
  phase2_running:    { label: '建模求解中', color: '#3b82f6', icon: '▶' },
  peer_review:       { label: '同行评议',  color: '#8b5cf6', icon: '👁' },
  revising:          { label: '返修中',  color: '#f59e0b', icon: '↻' },
  finalizing:        { label: '收尾中',  color: '#3b82f6', icon: '▶' },
  completed:         { label: '已完成',  color: '#16a34a', icon: '✓' },
  failed:            { label: '失败',   color: '#dc2626', icon: '✗' },
  paused:            { label: '已暂停',  color: '#6b7280', icon: '⏸' },
};

export function TaskStatusBadge({ state, progressPercentage, compact }: TaskStatusBadgeProps) {
  const meta = STATE_META[state] ?? STATE_META.idle;
  return (
    <div
      data-testid={`task-status-${state}`}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: compact ? '2px 8px' : '4px 12px',
        background: meta.color + '15',
        color: meta.color,
        border: `1px solid ${meta.color}40`,
        borderRadius: compact ? 4 : 6,
        fontSize: compact ? 11 : 13,
        fontWeight: 500,
      }}
    >
      <span>{meta.icon}</span>
      <span>{meta.label}</span>
      {progressPercentage !== undefined && progressPercentage < 100 && (
        <span style={{ marginLeft: 4, opacity: 0.7 }}>{Math.round(progressPercentage)}%</span>
      )}
    </div>
  );
}
