'use client';

/**
 * Camera-Ready 面板（Phase 6）。
 *
 * 用户原话：「最终输出的产品是可直接交付的」。
 * 本组件负责：
 * - 调 POST /tasks/{id}/camera-ready 触发打包
 * - 显示 zip 大小 / 章节树 / bib 条目数
 * - 提供下载按钮
 * - 显示 skipped_reasons（如缺主 tex / 缺 figures / 缺 code）
 */

import React, { useState, useCallback } from 'react';
import { useTheme } from '@/hooks/useTheme';

interface CameraReadyResponse {
  output_dir: string;
  zip_path: string | null;
  skipped_reasons: string[];
  artifact_summary: {
    figures: number;
    code_files: number;
    bib_entries: number;
    chapters: number;
  };
}

interface CameraReadyPanelProps {
  taskId: string;
  templateId?: string;
  apiBase?: string;
}

export function CameraReadyPanel({ taskId, templateId, apiBase }: CameraReadyPanelProps) {
  const base = apiBase || (typeof window !== 'undefined' && (window as any).__API_BASE__) || 'http://localhost:8000/api/v1';
  const [status, setStatus] = useState<CameraReadyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { theme } = useTheme();
  const dark = theme === 'dark';

  const build = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${base}/tasks/${taskId}/camera-ready`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_id: templateId,
          make_zip: true,
          max_zip_mb: 50,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data: CameraReadyResponse = await res.json();
      setStatus(data);
    } catch (e: any) {
      setError(e?.message ?? 'build failed');
    } finally {
      setLoading(false);
    }
  }, [taskId, templateId, base]);

  return (
    <div style={{
      padding: 16,
      border: `1px solid ${dark ? '#475569' : '#e5e7eb'}`,
      borderRadius: 8,
      background: dark ? '#1e293b' : '#f9fafb',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 16, color: dark ? '#f1f5f9' : '#111827' }}>📦 Camera-Ready 打包</h3>
        <button
          type="button"
          onClick={build}
          disabled={loading}
          data-testid="camera-ready-build"
          style={{
            padding: '8px 16px', background: '#2563eb', color: 'white',
            border: 'none', borderRadius: 6, cursor: loading ? 'wait' : 'pointer',
            fontSize: 13, fontWeight: 500,
          }}
        >
          {loading ? '打包中…' : status ? '重新打包' : '生成 Camera-Ready zip'}
        </button>
      </div>

      {error && (
        <div style={{
          padding: 10, marginBottom: 12, borderRadius: 6, fontSize: 13,
          background: dark ? '#7f1d1d' : '#fee2e2',
          color: dark ? '#fca5a5' : '#991b1b',
        }}>
          ⚠ {error}
        </div>
      )}

      {status && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 12 }}>
            <Metric label="图表" value={status.artifact_summary.figures} dark={dark} />
            <Metric label="代码" value={status.artifact_summary.code_files} dark={dark} />
            <Metric label="引用" value={status.artifact_summary.bib_entries} dark={dark} />
            <Metric label="章节" value={status.artifact_summary.chapters} dark={dark} />
          </div>

          {status.skipped_reasons.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: dark ? '#94a3b8' : '#6b7280', marginBottom: 4 }}>缺失记录：</div>
              {status.skipped_reasons.map((r, i) => (
                <div key={i} style={{ fontSize: 12, color: dark ? '#fbbf24' : '#b45309', padding: '2px 0' }}>
                  • {r}
                </div>
              ))}
            </div>
          )}

          {status.zip_path && (
            <a
              href={status.zip_path.startsWith('http') ? status.zip_path : `${base.replace('/api/v1', '')}${status.zip_path}`}
              download
              data-testid="camera-ready-download"
              style={{
                display: 'inline-block', padding: '10px 20px',
                background: '#16a34a', color: 'white', textDecoration: 'none',
                borderRadius: 6, fontSize: 13, fontWeight: 500,
              }}
            >
              ⬇ 下载 zip
            </a>
          )}

          <details style={{ marginTop: 12, fontSize: 12 }}>
            <summary style={{ cursor: 'pointer', color: dark ? '#94a3b8' : '#6b7280' }}>产物目录</summary>
            <code style={{
              display: 'block', padding: 8, marginTop: 4, borderRadius: 4,
              background: dark ? '#0f172a' : '#f3f4f6',
              color: dark ? '#94a3b8' : '#374151',
            }}>
              {status.output_dir}
            </code>
          </details>
        </>
      )}
    </div>
  );
}

function Metric({ label, value, dark }: { label: string; value: number; dark: boolean }) {
  return (
    <div style={{
      padding: 10, borderRadius: 6, textAlign: 'center',
      background: dark ? '#0f172a' : 'white',
      border: `1px solid ${dark ? '#475569' : '#e5e7eb'}`,
    }}>
      <div style={{ fontSize: 24, fontWeight: 600, color: dark ? '#f1f5f9' : '#1f2937' }}>{value}</div>
      <div style={{ fontSize: 12, color: dark ? '#94a3b8' : '#6b7280' }}>{label}</div>
    </div>
  );
}
