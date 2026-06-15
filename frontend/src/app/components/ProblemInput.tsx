'use client';

import { useState, useRef, useEffect } from 'react';
import styles from './ProblemInput.module.css';
import { useAppStore } from '../store/useAppStore';
import { TemplateSelector, TEMPLATE_OPTIONS } from './TemplateSelector';

const WORKFLOWS = [
  { id: 'standard', name: '标准流程', desc: '分析→数据→文献→建模→求解→论文→评议（推荐）' },
  { id: 'quick', name: '快速生成', desc: '跳过文献搜集，适合已知领域的研究问题' },
  { id: 'deep_research', name: '深度研究', desc: '多轮文献搜集 + 团队讨论，适合陌生前沿领域' },
  { id: 'code_focused', name: '代码优先', desc: '跳过文献，强化求解与调试，适合计算密集型问题' },
  { id: 'research_paper', name: 'CCF-A 论文', desc: '完整科研流程：实验设计→建模→求解→论文→同行评议→修订' },
];

// Phase 6: 8 模板统一管理（4 旧 + 4 新 CCF-A 目标）。
// 旧 hardcoded 4 模板已被 TemplateSelector 组件替代。
const TEMPLATES = TEMPLATE_OPTIONS;

interface ProblemInputProps {
  onSubmit: (params: {
    problemText: string;
    projectName: string;
    workflow: string;
    template: string;
    mode: string;
    useCritique: boolean;
    knowledgeBaseId: string | null;
    dataSource: 'upload' | 'self_collect' | 'upload_and_collect';
    problemType: string;
    dataFiles: string[];
  }) => void;
  submitting: boolean;
  taskStatus: string;
  progress: number;
}

export default function ProblemInput({ onSubmit, submitting, taskStatus, progress }: ProblemInputProps) {
  const projects = useAppStore((s) => s.projects);
  const activeProjectId = useAppStore((s) => s.activeProjectId);
  const setActiveProject = useAppStore((s) => s.setActiveProject);
  const createProject = useAppStore((s) => s.createProject);
  const deleteProject = useAppStore((s) => s.deleteProject);
  const loadProjects = useAppStore((s) => s.loadProjects);

  const activeProject = projects.find((p) => p.id === activeProjectId);
  const selectedFiles = useAppStore((s) => s.selectedFiles);
  const [projectName, setProjectName] = useState(activeProject?.name || '');
  const [problemText, setProblemText] = useState('');
  const [workflow, setWorkflow] = useState('standard');
  const [template, setTemplate] = useState('math_modeling');
  const [dataSource, setDataSource] = useState<'upload' | 'self_collect' | 'upload_and_collect'>('upload');
  const [problemType, setProblemType] = useState('未知');
  const [useCritique, setUseCritique] = useState(true);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [showNewProject, setShowNewProject] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Knowledge base selector
  const knowledgeBases = useAppStore((s) => s.knowledgeBases);
  const activeKnowledgeBaseId = useAppStore((s) => s.activeKnowledgeBaseId);
  const [knowledgeBaseId, setKnowledgeBaseId] = useState<string | null>(activeKnowledgeBaseId);

  const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

  // 加载项目列表
  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    if (activeProject) setProjectName(activeProject.name);
  }, [activeProjectId]);

  const handleOcrUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setOcrLoading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(apiBase() + '/data/ocr', { method: 'POST', body: formData });
      const data = await res.json();
      const text = data.text || '';
      if (text) {
        setProblemText(prev => prev ? prev + '\n\n--- OCR识别内容 ---\n' + text : text);
      }
    } catch {} finally { setOcrLoading(false); }
  };

  const handleCreateProject = async () => {
    const name = newProjectName.trim();
    if (!name) { alert('请输入项目名称'); return; }
    const id = await createProject(name);
    setActiveProject(id);
    setProjectName(name);
    setShowNewProject(false);
    setNewProjectName('');
  };

  const handleSubmit = () => {
    if (!problemText.trim()) { alert('请输入问题描述'); return; }
    const finalProjectName = projectName.trim() || activeProject?.name || '未命名项目';
    const dataFiles = selectedFiles.size > 0 ? Array.from(selectedFiles) : [];
    onSubmit({
      problemText,
      projectName: finalProjectName,
      workflow,
      template,
      mode: 'sequential',
      useCritique,
      knowledgeBaseId,
      dataSource,
      problemType,
      dataFiles,
    });
  };

  const isRunning = taskStatus === 'running' || taskStatus === 'phase1' || taskStatus === 'phase2';

  return (
    <div className={styles.container}>
      <div className={styles.section}>
        <div className={styles.sectionTitle}>📝 研究问题输入</div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem' }}>
          <select
            style={{ flex: 1, padding: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }}
            value={activeProjectId || ''}
            onChange={e => {
              const id = e.target.value;
              if (id === '__new__') { setShowNewProject(true); return; }
              setActiveProject(id || null);
              const p = projects.find((pr) => pr.id === id);
              if (p) setProjectName(p.name);
            }}
          >
            <option value="">全局项目池</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
            <option value="__new__">+ 新建项目</option>
          </select>
          {activeProjectId && (
            <button
              title="删除当前项目"
              onClick={async () => {
                if (!confirm('确定要删除该项目吗？关联的任务记录不会受影响。')) return;
                await deleteProject(activeProjectId);
                setProjectName('');
              }}
              style={{
                padding: '0.4rem 0.6rem',
                background: 'rgba(231,76,60,0.15)',
                border: '1px solid rgba(231,76,60,0.3)',
                borderRadius: 6,
                color: '#e74c3c',
                cursor: 'pointer',
                fontSize: '0.8rem',
              }}
            >
              🗑️ 删除
            </button>
          )}
          {showNewProject && (
            <div style={{ display: 'flex', gap: '0.3rem', alignItems: 'center' }}>
              <input
                style={{ padding: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem', width: 140 }}
                placeholder="项目名称"
                value={newProjectName}
                onChange={e => setNewProjectName(e.target.value)}
                maxLength={60}
              />
              <button onClick={handleCreateProject} style={{ padding: '0.4rem 0.6rem', background: 'linear-gradient(135deg, #2ecc71, #27ae60)', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: '0.8rem' }}>创建</button>
              <button onClick={() => setShowNewProject(false)} style={{ padding: '0.4rem 0.6rem', background: 'rgba(231,76,60,0.15)', border: '1px solid rgba(231,76,60,0.3)', borderRadius: 6, color: '#e74c3c', cursor: 'pointer', fontSize: '0.8rem' }}>取消</button>
            </div>
          )}
        </div>
        <input
          className={styles.projectInput}
          placeholder="输入项目名称（如：多智能体记忆机制研究 / 供应链优化 / CCF-A 论文）"
          value={projectName}
          onChange={e => setProjectName(e.target.value)}
          maxLength={60}
        />
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '0.5rem' }}>
          <select
            style={{ flex: 1, padding: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }}
            value={knowledgeBaseId || ''}
            onChange={e => setKnowledgeBaseId(e.target.value || null)}
          >
            <option value="">📚 使用所有知识库</option>
            {knowledgeBases.map((kb) => (
              <option key={kb.id} value={kb.id}>{kb.name}</option>
            ))}
          </select>
        </div>
        <div className={styles.ocrRow}>
          <label className={styles.ocrBtn}>
            {ocrLoading ? '识别中...' : '📷 上传问题图片 / PDF（OCR 提取文本）'}
            <input type="file" accept="image/*,.pdf" onChange={handleOcrUpload} style={{ display: 'none' }} disabled={ocrLoading} />
          </label>
          <span className={styles.hint}>支持 JPG / PNG / PDF，自动提取文本</span>
        </div>
        <textarea
          className={styles.textarea}
          placeholder={'请描述您的研究问题，包括：\n1. 研究背景与目标\n2. 具体要求（优化/预测/评价/分类/仿真等）\n3. 数据情况（如有数据文件，请先到「数据」标签上传；无数据可选"系统自动搜集"）\n4. 约束条件或特殊要求\n5. 目标投稿会议/期刊（可选，系统会自动推荐模板）'}
          value={problemText}
          onChange={e => setProblemText(e.target.value)}
          rows={10}
        />

        <div style={{ marginTop: '0.8rem', display: 'grid', gap: '0.6rem', gridTemplateColumns: '1fr 1fr' }}>
          <div>
            <div className={styles.optionLabel}>问题类型</div>
            <select
              style={{ width: '100%', padding: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }}
              value={problemType}
              onChange={e => setProblemType(e.target.value)}
            >
              <option value="未知">未知 / 自动判断</option>
              <option value="优化">优化</option>
              <option value="预测">预测</option>
              <option value="评价">评价</option>
              <option value="分类">分类</option>
              <option value="仿真">仿真</option>
              <option value="网络">网络</option>
              <option value="物理">物理</option>
              <option value="测量">测量</option>
              <option value="综合">综合</option>
            </select>
          </div>
          <div>
            <div className={styles.optionLabel}>数据来源</div>
            <select
              style={{ width: '100%', padding: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }}
              value={dataSource}
              onChange={e => setDataSource(e.target.value as any)}
            >
              <option value="upload">我会上传数据</option>
              <option value="self_collect">无数据，让系统自己搜集</option>
              <option value="upload_and_collect">我上传数据，系统再补全</option>
            </select>
          </div>
        </div>

        {dataSource !== 'self_collect' && (
          <div style={{ marginTop: '0.5rem', color: '#aaa', fontSize: '0.8rem' }}>
            已勾选 {selectedFiles.size} 个数据文件（请到「数据」标签上传并勾选）
          </div>
        )}
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>⚙️ 工作流与模板</div>

        <div className={styles.optionGroup}>
          <div className={styles.optionLabel}>工作流模式（系统会根据问题自动推荐，您也可以手动选择）</div>
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
          <div className={styles.optionLabel}>论文模板（{TEMPLATES.length} 选 1）</div>
          <TemplateSelector
            value={template}
            onChange={(t) => setTemplate(t)}
            disabled={submitting}
          />
        </div>

        <div className={styles.optionGroup}>
          <label className={styles.toggle}>
            <input type="checkbox" checked={useCritique} onChange={e => setUseCritique(e.target.checked)} />
            <span className={styles.toggleTrack}>
              <span className={styles.toggleThumb} />
            </span>
            <span className={styles.toggleLabel}>启用自评质量循环（Writer 自评 + 自动重写，推荐开启）</span>
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
          {submitting ? '🚀 启动中...' : isRunning ? `🔄 生成中 ${progress}%` : '🚀 启动多智能体协作生成'}
        </button>
      </div>
    </div>
  );
}
