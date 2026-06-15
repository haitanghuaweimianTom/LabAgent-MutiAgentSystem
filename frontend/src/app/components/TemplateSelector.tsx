'use client';

/**
 * 论文模板选择器（Phase 6）。
 *
 * 8 个模板：4 旧（向后兼容） + 4 新 CCF-A 目标。
 * 用户在前端可选 → POST /tasks/submit 的 options.template 字段。
 *
 * 用户原话：「生产的可交付结果应该在前端可以选类型的」「严格控制幻觉」
 * 「不许搞成只能生成某一类的结果」——本组件是这条约束的 UI 实现。
 */

import React from 'react';

export interface TemplateOption {
  id: string;
  name: string;
  desc: string;
  chapters: number;
  domain: 'math_modeling' | 'coursework' | 'financial_analysis' | 'research_survey' | 'research_paper';
  ccfA?: boolean;  // 是否 CCF-A 目标模板
  recommended?: boolean;
}

export const TEMPLATE_OPTIONS: TemplateOption[] = [
  // 旧 4 套（保留，向后兼容）
  {
    id: 'math_modeling',
    name: '数学建模',
    desc: '12章 CUMCM 标准结构（mcmthesis 排版），适合数学建模竞赛',
    chapters: 12,
    domain: 'math_modeling',
  },
  {
    id: 'coursework',
    name: '课程作业 / 学术报告',
    desc: '8章简化结构，适合课程报告 / 学术作业',
    chapters: 8,
    domain: 'coursework',
  },
  {
    id: 'financial_analysis',
    name: '金融分析报告',
    desc: '10章投资分析 / 风险评估 / 量化策略',
    chapters: 10,
    domain: 'financial_analysis',
  },
  {
    id: 'research_survey',
    name: '研究调研报告',
    desc: '10章文献综述 / 研究现状 / 未来方向',
    chapters: 10,
    domain: 'research_survey',
  },
  // 新 4 套 CCF-A 目标
  {
    id: 'ieee_conference',
    name: 'IEEE Conference (S&P / CCS / SIGCOMM / VLDB)',
    desc: '双栏会议，8-12 页，Related Work + Method + Experiments',
    chapters: 11,
    domain: 'research_paper',
    ccfA: true,
    recommended: true,
  },
  {
    id: 'neurips_2024',
    name: 'NeurIPS / ICML / ICLR',
    desc: '9 页主体，匿名 double-blind，Theoretical + Empirical',
    chapters: 10,
    domain: 'research_paper',
    ccfA: true,
  },
  {
    id: 'acm_sigconf',
    name: 'ACM SIG (SIGGRAPH / MobiCom / CHI)',
    desc: 'acmart 双栏，CCS Concepts 关键词',
    chapters: 10,
    domain: 'research_paper',
    ccfA: true,
  },
  {
    id: 'springer_lncs',
    name: 'Springer LNCS (EuroSys / IFIP)',
    desc: 'llncs 双栏，splncs04 引用格式',
    chapters: 8,
    domain: 'research_paper',
    ccfA: true,
  },
];

interface TemplateSelectorProps {
  value: string;
  onChange: (templateId: string) => void;
  showCcfABadge?: boolean;
  disabled?: boolean;
}

export function TemplateSelector({ value, onChange, showCcfABadge = true, disabled }: TemplateSelectorProps) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 }}>
      {TEMPLATE_OPTIONS.map((tpl) => {
        const selected = tpl.id === value;
        return (
          <button
            key={tpl.id}
            type="button"
            onClick={() => !disabled && onChange(tpl.id)}
            disabled={disabled}
            data-testid={`template-${tpl.id}`}
            style={{
              padding: 12,
              textAlign: 'left',
              border: selected ? '2px solid #2563eb' : '1px solid #d1d5db',
              borderRadius: 8,
              background: selected ? '#eff6ff' : '#fff',
              cursor: disabled ? 'not-allowed' : 'pointer',
              opacity: disabled ? 0.6 : 1,
              transition: 'all 0.15s',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontWeight: 600, fontSize: 14 }}>{tpl.name}</span>
              <span style={{ display: 'flex', gap: 4 }}>
                {tpl.recommended && (
                  <span style={{
                    fontSize: 10, padding: '2px 6px', borderRadius: 4,
                    background: '#fef3c7', color: '#92400e', fontWeight: 600,
                  }}>
                    推荐
                  </span>
                )}
                {showCcfABadge && tpl.ccfA && (
                  <span style={{
                    fontSize: 10, padding: '2px 6px', borderRadius: 4,
                    background: '#dbeafe', color: '#1e40af', fontWeight: 600,
                  }}>
                    CCF-A
                  </span>
                )}
              </span>
            </div>
            <div style={{ fontSize: 12, color: '#6b7280', lineHeight: 1.5 }}>{tpl.desc}</div>
            <div style={{ marginTop: 6, fontSize: 11, color: '#9ca3af' }}>
              {tpl.chapters} 章节 · {tpl.domain}
            </div>
          </button>
        );
      })}
    </div>
  );
}
