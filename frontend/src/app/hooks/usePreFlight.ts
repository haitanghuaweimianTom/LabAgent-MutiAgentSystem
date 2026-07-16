'use client';

import { useState, useCallback } from 'react';

export interface PreflightReport {
  problem_type: string;
  has_data_confidence: number;
  data_subjects: string[];
  recommended_template: string;
  recommended_workflow: string;
  recommended_mode: string;
  data_adequacy: 'sufficient' | 'insufficient' | 'missing';
  llm_should_collect: boolean;
  collection_plan: string;
  data_mismatch_warning?: string | null;
  data_schemas?: any[];
}

interface UsePreFlightResult {
  report: PreflightReport | null;
  loading: boolean;
  error: string | null;
  fetch: (taskId: string) => Promise<void>;
}

const apiBase = () => (typeof window !== 'undefined' && (window as any).__API_BASE__) || 'http://localhost:8001/api/v1';

export function usePreFlight(): UsePreFlightResult {
  const [report, setReport] = useState<PreflightReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchReport = useCallback(async (taskId: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase()}/tasks/${taskId}/preflight`, { method: 'POST' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail?.message || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setReport(data.preflight_report || data);
    } catch (e: any) {
      setError(e?.message ?? 'preflight 请求失败');
    } finally {
      setLoading(false);
    }
  }, []);

  return { report, loading, error, fetch: fetchReport };
}
