'use client';

import { useState, useRef } from 'react';
import styles from './ProblemInput.module.css';

const WORKFLOWS = [
  { id: 'standard', name: '标准流程', desc: '研究→分析→建模→求解→论文（推荐）' },
  { id: 'quick', name: '快速生成', desc: '跳过研究阶段，适合已知问题' },
  { id: 'deep_research', name: '深度研究', desc: '强化资料搜集，适合陌生领域' },
  { id: 'code_focused', name: '代码优先', desc: '强化求解与调试，适合计算密集型' },
];

const TEMPLATES = [
  { id: 'math_modeling', name: '数学建模竞赛', desc: '12章标准结构，MCM/ICM/高教社杯', chapters: 12 },
  { id: 'coursework', name: '课程作业', desc: '8章简化结构，适合课程报告', chapters: 8 },
  { id: 'financial_analysis', name: '金融分析报告', desc: '10章投资分析结构', chapters: 10 },
];

const SOLVE_MODES = [
  { id: 'sequential', name: '逐个递进', desc: '前序结果递进至后序' },
  { id: 'batch', name: '批量并行', desc: '各子问题独立求解' },
];

interface ProblemInputProps {
  onSubmit: (params: {
    problemText: string;
    workflow: string;
    template: string;
    mode: string;
    useCritique: boolean;
  }) => void;
  submitting: boolean;
  taskStatus: string;
  progress: number;
}

export default function ProblemInput({ onSubmit, submitting, taskStatus, progress }: ProblemInputProps) {
  const [problemText, setProblemText] = useState('');
  const [workflow, setWorkflow] = useState('standard');
  const [template, setTemplate] = useState('math_modeling');
  const [mode, setMode] = useState('sequential');
  const [useCritique, setUseCritique] = useState(true);
  const [ocrLoading, setOcrLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

  const handleOcrUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setOcrLoading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(apiBase() + '/data/upload', { method: 'POST', body: formData });
      const data = await res.json();
      const text = data.cleaned_text || data.raw_text || '';
      if (text) {
        setProblemText(prev => prev ? prev + '\n\n--- OCR识别内容 ---\n' + text : text);
      }
    } catch {} finally { setOcrLoading(false); }
  };

  const handleSubmit = () => {
    if (!problemText.trim()) { alert('请输入问题描述'); return; }
    onSubmit({ problemText, workflow, template, mode, useCritique });
  };

  const isRunning = taskStatus === 'running' || taskStatus === 'phase1' || taskStatus === 'phase2';

  return (
    <div className={styles.container}>
      <div className={styles.section}>
        <div className={styles.sectionTitle}>📝 赛题输入</div>
        <div className={styles.ocrRow}>
          <label className={styles.ocrBtn}>
            {ocrLoading ? '识别中...' : '📷 上传题目图片 / PDF'}
            <input type="file" accept="image/*,.pdf" onChange={handleOcrUpload} style={{ display: 'none' }} disabled={ocrLoading} />
          </label>
          <span className={styles.hint}>支持 JPG / PNG / PDF，自动提取文本</span>
        </div>
        <textarea
          className={styles.textarea}
          placeholder={'请描述数学建模问题，包括：\n1. 问题背景\n2. 具体要求（预测/优化/评价等）\n3. 约束条件\n4. 如有数据文件，请先到「数据」标签上传'}
          value={problemText}
          onChange={e => setProblemText(e.target.value)}
          rows={10}
        />
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>⚙️ 工作流配置</div>

        <div className={styles.optionGroup}>
          <div className={styles.optionLabel}>工作流模式</div>
          <div className={styles.optionCards}>
            {WORKFLOWS.map(wf => (
              <div
                key={wf.id}
                className={`${styles.optionCard} ${workflow === wf.id ? styles.optionCardActive : ''}`}
                onClick={() => setWorkflow(wf.id)}
              >
                <div className={styles.optionCardName}>{wf.name}</div>
                <div className={styles.optionCardDesc}>{wf.desc}</div>
              </div>
            ))}
          </div>
        </div>

        <div className={styles.optionGroup}>
          <div className={styles.optionLabel}>论文模板</div>
          <div className={styles.optionCards}>
            {TEMPLATES.map(tpl => (
              <div
                key={tpl.id}
                className={`${styles.optionCard} ${template === tpl.id ? styles.optionCardActive : ''}`}
                onClick={() => setTemplate(tpl.id)}
              >
                <div className={styles.optionCardName}>{tpl.name}</div>
                <div className={styles.optionCardDesc}>{tpl.desc}</div>
                <div className={styles.optionCardMeta}>{tpl.chapters} 章</div>
              </div>
            ))}
          </div>
        </div>

        <div className={styles.optionGroup}>
          <div className={styles.optionLabel}>求解策略</div>
          <div className={styles.inlineOptions}>
            {SOLVE_MODES.map(sm => (
              <label key={sm.id} className={`${styles.inlineOption} ${mode === sm.id ? styles.inlineOptionActive : ''}`}>
                <input type="radio" name="solveMode" value={sm.id} checked={mode === sm.id} onChange={() => setMode(sm.id)} />
                <span className={styles.inlineName}>{sm.name}</span>
                <span className={styles.inlineDesc}>{sm.desc}</span>
              </label>
            ))}
          </div>
        </div>

        <div className={styles.optionGroup}>
          <label className={styles.toggle}>
            <input type="checkbox" checked={useCritique} onChange={e => setUseCritique(e.target.checked)} />
            <span className={styles.toggleTrack}>
              <span className={styles.toggleThumb} />
            </span>
            <span className={styles.toggleLabel}>启用 Critique-Improvement 质量循环（推荐，会增加耗时）</span>
          </label>
        </div>
      </div>

      {isRunning && (
        <div className={styles.progressSection}>
          <div className={styles.progressBar}>
            <div className={styles.progressFill} style={{ width: progress + '%' }} />
          </div>
          <div className={styles.progressText}>{progress}% · 生成中...</div>
        </div>
      )}

      <div className={styles.btnRow}>
        <button className={styles.submitBtn} onClick={handleSubmit} disabled={submitting || !problemText.trim() || isRunning}>
          {submitting ? '🚀 启动中...' : isRunning ? `🔄 生成中 ${progress}%` : '🚀 启动全自动生成'}
        </button>
      </div>
    </div>
  );
}
