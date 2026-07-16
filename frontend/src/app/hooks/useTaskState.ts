'use client';

/**
 * 任务状态机 hook（Phase 6）。
 *
 * 9 阶段状态枚举与后端 orchestrator 对齐：
 *   idle / phase1_running / phase1_reviewing
 *   / phase2_running / peer_review / revising
 *   / finalizing / completed / failed / paused
 *
 * 数据流：
 * - 初始化时 GET /tasks/{id} 拉取全量状态
 * - 通过 SSE /tasks/{id}/stream 订阅 phase_changed 事件
 * - WS 断线时自动重连；重连成功后重新 GET 全量
 */

import { useEffect, useState, useRef, useCallback } from 'react';

export type TaskStateName =
  | 'idle'
  | 'preflight_running'
  | 'self_collecting_data'
  | 'iterating_solver'
  | 'cannot_solve'
  | 'phase1_running'
  | 'phase1_reviewing'
  | 'phase2_running'
  | 'peer_review'
  | 'revising'
  | 'finalizing'
  | 'completed'
  | 'failed'
  | 'paused';

export interface TaskState {
  taskId: string;
  name: TaskStateName;
  progressPercentage: number;
  currentStep: string;
  error?: string | null;
  templateId?: string;
  peerReview?: {
    overallScore: number;
    recommendation: 'accept' | 'revise' | 'reject';
  } | null;
}

const STATE_RANK: Record<TaskStateName, number> = {
  idle: 0,
  preflight_running: 1,
  self_collecting_data: 2,
  phase1_running: 3,
  phase1_reviewing: 4,
  phase2_running: 5,
  iterating_solver: 5,
  peer_review: 6,
  revising: 7,
  finalizing: 8,
  completed: 9,
  failed: 9,
  cannot_solve: 9,
  paused: 1,
};

export function rankState(s: TaskStateName): number {
  return STATE_RANK[s] ?? 0;
}

export function isTerminalState(s: TaskStateName): boolean {
  return s === 'completed' || s === 'failed';
}

interface UseTaskStateOptions {
  taskId: string | null;
  apiBase?: string;
  /** 是否启用 SSE 实时订阅。默认 true。 */
  subscribe?: boolean;
  /** 断线重连间隔 ms。默认 3000。 */
  reconnectMs?: number;
}

export function useTaskState(options: UseTaskStateOptions): {
  state: TaskState | null;
  error: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
} {
  const { taskId, subscribe = true, reconnectMs = 3000 } = options;
  const apiBase = options.apiBase || (typeof window !== 'undefined' && (window as any).__API_BASE__) || 'http://localhost:8001/api/v1';

  const [state, setState] = useState<TaskState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchState = useCallback(async () => {
    if (!taskId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/tasks/${taskId}/status`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      }
      const data = await res.json();
      setState({
        taskId,
        name: mapBackendStatusToState(data.status, data.current_step),
        progressPercentage: data.progress_percentage ?? 0,
        currentStep: data.current_step ?? '',
        error: data.error,
        templateId: data.template_id ?? data.template ?? '',
        peerReview: data.peer_review
          ? {
              overallScore: data.peer_review.overall_score ?? 0,
              recommendation: normalizeRecommendation(data.peer_review.recommendation),
            }
          : null,
      });
    } catch (e: any) {
      setError(e?.message ?? 'failed to fetch task state');
    } finally {
      setLoading(false);
    }
  }, [taskId, apiBase]);

  // SSE 订阅
  useEffect(() => {
    if (!taskId || !subscribe) return;

    const connect = () => {
      try {
        const es = new EventSource(`${apiBase}/tasks/${taskId}/stream`);
        esRef.current = es;

        es.addEventListener('phase_changed', (evt: MessageEvent) => {
          try {
            const payload = JSON.parse(evt.data);
            setState((prev) => {
              if (!prev) return null;
              const next: TaskState = { ...prev, ...payload };
              if (payload.template_id || payload.template) {
                next.templateId = payload.template_id ?? payload.template;
              }
              if (payload.peer_review) {
                next.peerReview = {
                  overallScore: payload.peer_review.overall_score ?? 0,
                  recommendation: normalizeRecommendation(payload.peer_review.recommendation),
                };
              }
              if (payload.name && isValidStateName(payload.name)) {
                next.name = payload.name;
              }
              return next;
            });
          } catch {
            // ignore parse errors
          }
        });

        es.addEventListener('peer_review_done', (evt: MessageEvent) => {
          try {
            const payload = JSON.parse(evt.data);
            setState((prev) => prev ? {
              ...prev,
              name: 'peer_review',
              peerReview: {
                overallScore: payload.overall_score ?? 0,
                recommendation: payload.recommendation ?? 'revise',
              },
            } : null);
          } catch { /* ignore */ }
        });

        es.addEventListener('revision_done', (evt: MessageEvent) => {
          try {
            const payload = JSON.parse(evt.data);
            setState((prev) => prev ? {
              ...prev,
              name: 'revising',
              peerReview: {
                overallScore: payload.overall_score ?? 0,
                recommendation: payload.recommendation ?? 'revise',
              },
            } : null);
          } catch { /* ignore */ }
        });

        es.onerror = () => {
          es.close();
          esRef.current = null;
          // 自动重连
          if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
          reconnectTimerRef.current = setTimeout(connect, reconnectMs);
        };
      } catch (e) {
        // ignore
      }
    };

    connect();
    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };
  }, [taskId, apiBase, subscribe, reconnectMs]);

  // 初始 fetch + 每次 taskId 变化时重新拉
  useEffect(() => {
    fetchState();
  }, [fetchState]);

  return { state, error, loading, refresh: fetchState };
}

function mapBackendStatusToState(status: string, currentStep: string): TaskStateName {
  const s = (status ?? '').toLowerCase();
  if (s === 'completed') return 'completed';
  if (s === 'failed') return 'failed';
  if (s === 'paused' || s === 'interrupted') return 'paused';
  if (s === 'preflight_running') return 'preflight_running';
  if (s === 'self_collecting_data') return 'self_collecting_data';
  if (s === 'cannot_solve') return 'cannot_solve';
  if (s === 'phase1_completed' || s === 'phase1_completed_reviewing') return 'phase1_reviewing';
  if (s === 'phase2_running' || s === 'running') {
    if (currentStep?.includes('iterat')) return 'iterating_solver';
    if (currentStep?.includes('peer_review')) return 'peer_review';
    if (currentStep?.includes('revise')) return 'revising';
    if (currentStep?.includes('final')) return 'finalizing';
    return 'phase2_running';
  }
  if (s === 'phase1_running') return 'phase1_running';
  return 'phase1_running';
}

function isValidStateName(name: string): name is TaskStateName {
  return [
    'idle',
    'preflight_running',
    'self_collecting_data',
    'iterating_solver',
    'cannot_solve',
    'phase1_running',
    'phase1_reviewing',
    'phase2_running',
    'peer_review',
    'revising',
    'finalizing',
    'completed',
    'failed',
    'paused',
  ].includes(name);
}

function normalizeRecommendation(r: string): 'accept' | 'revise' | 'reject' {
  const s = (r ?? '').toLowerCase();
  if (s.includes('accept')) return 'accept';
  if (s.includes('reject')) return 'reject';
  return 'revise';
}
