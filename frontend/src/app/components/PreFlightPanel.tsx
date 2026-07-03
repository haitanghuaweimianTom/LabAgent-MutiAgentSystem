'use client';

import React from 'react';

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

interface PreFlightPanelProps {
  report: PreflightReport;
  onConfirm?: () => void;
  onAdjust?: () => void;
  onApplyRecommended?: (template: string, workflow: string, mode: string) => void;
}

const ADEQUACY_LABEL: Record<string, { label: string; color: string }> = {
  sufficient: { label: '数据充足', color: '#16a34a' },
  insufficient: { label: '数据不足', color: '#f59e0b' },
  missing: { label: '缺少数据', color: '#dc2626' },
};

export function PreFlightPanel({ report, onConfirm, onAdjust, onApplyRecommended }: PreFlightPanelProps) {
  const adequacy = ADEQUACY_LABEL[report.data_adequacy] || { label: report.data_adequacy, color: '#9ca3af' };

  return (
    <div style={{ background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, padding: '1rem', marginTop: '1rem' }}>
      <div style={{ fontWeight: 600, fontSize: '1.05rem', marginBottom: '0.6rem', color: '#e0e0e0' }}>
        🔍 Preflight 预检报告
      </div>

      {report.data_mismatch_warning && (
        <div style={{ background: 'rgba(220,38,38,0.12)', border: '1px solid rgba(220,38,38,0.3)', borderRadius: 8, padding: '0.6rem', color: '#fca5a5', marginBottom: '0.6rem' }}>
          ⚠️ {report.data_mismatch_warning}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.9rem', color: '#ccc' }}>
        <div><strong>问题类型：</strong> {report.problem_type}</div>
        <div><strong>数据置信度：</strong> {(report.has_data_confidence * 100).toFixed(0)}%</div>
        <div><strong>推荐模板：</strong> {report.recommended_template}</div>
        <div><strong>推荐工作流：</strong> {report.recommended_workflow}</div>
        <div><strong>推荐模式：</strong> {report.recommended_mode}</div>
        <div>
          <strong>数据评估：</strong>
          <span style={{ color: adequacy.color, marginLeft: 4 }}>{adequacy.label}</span>
        </div>
      </div>

      {report.data_subjects?.length > 0 && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: '#aaa' }}>
          <strong>数据主题：</strong> {report.data_subjects.join('、')}
        </div>
      )}

      {report.collection_plan && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: '#aaa' }}>
          <strong>数据搜集计划：</strong>
          <div style={{ marginTop: '0.3rem', padding: '0.5rem', background: 'rgba(0,0,0,0.2)', borderRadius: 6 }}>
            {report.collection_plan}
          </div>
        </div>
      )}

      {(onConfirm || onAdjust || onApplyRecommended) && (
        <div style={{ marginTop: '0.8rem', display: 'flex', gap: '0.5rem' }}>
          {onApplyRecommended && (
            <button
              onClick={() => onApplyRecommended(report.recommended_template, report.recommended_workflow, report.recommended_mode)}
              style={{ padding: '0.4rem 0.8rem', background: 'linear-gradient(135deg, #9b59b6, #8e44ad)', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: '0.85rem' }}
            >
              🎯 应用推荐配置
            </button>
          )}
          {onConfirm && (
            <button
              onClick={onConfirm}
              style={{ padding: '0.4rem 0.8rem', background: 'linear-gradient(135deg, #2ecc71, #27ae60)', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: '0.85rem' }}
            >
              ✅ 确认推荐
            </button>
          )}
          {onAdjust && (
            <button
              onClick={onAdjust}
              style={{ padding: '0.4rem 0.8rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 6, color: '#3498db', cursor: 'pointer', fontSize: '0.85rem' }}
            >
              ⚙️ 调整配置
            </button>
          )}
        </div>
      )}
    </div>
  );
}
