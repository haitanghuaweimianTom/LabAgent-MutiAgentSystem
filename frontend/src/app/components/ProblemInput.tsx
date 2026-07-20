'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { useAppStore } from '../store/useAppStore';
import { TemplateSelector, TEMPLATE_OPTIONS } from './TemplateSelector';
import { apiBase } from '@/lib/api';

const WORKFLOWS = [
  { id: 'standard', name: '标准流程', desc: '分析→数据→文献→建模→求解→论文→评议（推荐）' },
  { id: 'quick', name: '快速生成', desc: '跳过文献搜集，适合已知领域的研究问题' },
  { id: 'deep_research', name: '深度研究', desc: '多轮文献搜集 + 团队讨论，适合陌生前沿领域' },
  { id: 'code_focused', name: '代码优先', desc: '跳过文献，强化求解与调试，适合计算密集型问题' },
  { id: 'research_paper', name: 'CCF-A 论文', desc: '完整科研流程：实验设计→建模→求解→论文→同行评议→修订' },
];

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
    knowledgeBaseIds: string[];
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

  const knowledgeBases = useAppStore((s) => s.knowledgeBases);
  const setKnowledgeBases = useAppStore((s) => s.setKnowledgeBases);
  const selectedKBIdsRaw = useAppStore((s) => s.selectedKBIds);
  const toggleKBSelection = useAppStore((s) => s.toggleKBSelection);
  const clearKBSelection = useAppStore((s) => s.clearKBSelection);
  const selectedKBIds: Set<string> = selectedKBIdsRaw instanceof Set
    ? selectedKBIdsRaw
    : new Set(Array.isArray(selectedKBIdsRaw) ? selectedKBIdsRaw : []);
  const [legacyKBId, setLegacyKBId] = useState<string | null>(null);

  useEffect(() => {
    loadProjects();
    loadKnowledgeBases();
  }, [loadProjects]);

  const loadKnowledgeBases = useCallback(async () => {
    try {
      const url = new URL(apiBase() + '/knowledge/bases');
      url.searchParams.set('include_task', 'false');
      const res = await fetch(url.toString());
      if (res.ok) {
        const data = await res.json();
        setKnowledgeBases(data.bases || []);
      }
    } catch {
      // ignore
    }
  }, [setKnowledgeBases]);

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
    const kbIds = selectedKBIds instanceof Set ? Array.from(selectedKBIds) : [];
    onSubmit({
      problemText,
      projectName: finalProjectName,
      workflow,
      template,
      mode: 'sequential',
      useCritique,
      knowledgeBaseId: kbIds.length === 1 ? kbIds[0] : legacyKBId,
      knowledgeBaseIds: kbIds,
      dataSource,
      problemType,
      dataFiles,
    });
  };

  const isRunning = taskStatus === 'running' || taskStatus === 'phase1' || taskStatus === 'phase2';

  const currentTemplate = TEMPLATE_OPTIONS.find((t) => t.id === template);
  const currentWorkflowName = WORKFLOWS.find((w) => w.id === workflow)?.name || workflow;

  return (
    <div className="flex flex-col gap-4">
      <div className="bg-[#1E293B] border border-[#334155] rounded-[14px] p-[1.2rem]">
        <div className="text-[1rem] text-[#F8FAFC] font-semibold mb-[0.8rem]">📝 研究问题输入</div>
        <div className="flex gap-2 items-center mb-2">
          <select
            className="flex-1 p-2 bg-black/30 border border-white/15 rounded-[8px] text-[#e0e0e0] text-[0.9rem]"
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
              className="py-[0.4rem] px-[0.6rem] bg-[rgba(231,76,60,0.15)] border border-[rgba(231,76,60,0.3)] rounded-[6px] text-[#e74c3c] cursor-pointer text-[0.8rem]"
            >
              🗑️ 删除
            </button>
          )}
          {showNewProject && (
            <div className="flex gap-[0.3rem] items-center">
              <input
                className="p-2 bg-black/30 border border-white/15 rounded-[8px] text-[#e0e0e0] text-[0.9rem] w-[140px]"
                placeholder="项目名称"
                value={newProjectName}
                onChange={e => setNewProjectName(e.target.value)}
                maxLength={60}
              />
              <button onClick={handleCreateProject} className="py-[0.4rem] px-[0.6rem] bg-gradient-to-br from-[#2ecc71] to-[#27ae60] text-white border-none rounded-[6px] cursor-pointer text-[0.8rem]">创建</button>
              <button onClick={() => setShowNewProject(false)} className="py-[0.4rem] px-[0.6rem] bg-[rgba(231,76,60,0.15)] border border-[rgba(231,76,60,0.3)] rounded-[6px] text-[#e74c3c] cursor-pointer text-[0.8rem]">取消</button>
            </div>
          )}
        </div>
        <input
          className="w-full py-[0.7rem] px-4 mb-[0.6rem] bg-black/30 border border-[#334155] rounded-[8px] text-[#e0e0e0] text-[0.95rem]"
          placeholder="输入项目名称（如：供应链优化 / CCF-A 论文 / 金融风控模型）"
          value={projectName}
          onChange={e => setProjectName(e.target.value)}
          maxLength={60}
        />
        <div className="mt-2">
          <div className="flex gap-2 items-center mb-[0.4rem]">
            <span className="text-[#94A3B8] text-[0.85rem]">
              📚 关联知识库（v5.4.0：可多选）
            </span>
            {selectedKBIds.size > 0 && (
              <button
                type="button"
                onClick={clearKBSelection}
                className="py-[0.2rem] px-[0.6rem] bg-transparent text-[#64748B] border border-[#334155] rounded-[6px] text-[0.78rem] cursor-pointer"
              >
                清空
              </button>
            )}
          </div>
          {knowledgeBases.length === 0 ? (
            <div className="p-2 text-[#64748B] text-[0.85rem] italic">
              暂无知识库；留空将自动使用项目私有 + 全局公共 KB
            </div>
          ) : (
            <div className="flex flex-wrap gap-[0.4rem]">
              {knowledgeBases.map((kb) => {
                const selected = selectedKBIds.has(kb.id);
                const isProject = (kb as any).scope === 'project';
                return (
                  <button
                    key={kb.id}
                    type="button"
                    onClick={() => toggleKBSelection(kb.id)}
                    title={(kb as any).description || kb.name}
                    className={cn(
                      'py-[0.35rem] px-[0.75rem] border rounded-[16px] cursor-pointer text-[0.85rem] transition-all duration-150',
                      selected
                        ? (isProject ? 'bg-[#8B5CF6] text-[#0F172A] border-[#A78BFA] font-semibold' : 'bg-[#2DD4BF] text-[#0F172A] border-[#5EEAD4] font-semibold')
                        : 'bg-black/30 text-[#CBD5E1] border-white/15 font-normal'
                    )}
                  >
                    {isProject ? '📁' : '🌐'} {kb.name}
                    {selected && ' ✓'}
                  </button>
                );
              })}
            </div>
          )}
          <div className="mt-[0.3rem] text-[#64748B] text-[0.75rem]">
            不选 = 自动注入「项目私有 + 全局公共」KB；勾选 = 仅使用勾选的 KB
          </div>
        </div>
        <div className="flex items-center gap-4 mb-[0.8rem]">
          <label className="inline-flex items-center gap-2 py-[0.6rem] px-[1.2rem] bg-[#F87171] text-[#F8FAFC] rounded-[8px] cursor-pointer text-[0.9375rem] font-semibold hover:-translate-y-[1px] transition-transform duration-200 disabled:opacity-60 disabled:cursor-not-allowed">
            {ocrLoading ? '识别中...' : '📷 上传问题图片 / PDF（OCR 提取文本）'}
            <input type="file" accept="image/*,.pdf" onChange={handleOcrUpload} className="hidden" disabled={ocrLoading} />
          </label>
          <span className="text-[#94A3B8] text-[0.9375rem]">支持 JPG / PNG / PDF，自动提取文本</span>
        </div>
        <textarea
          className="w-full p-4 bg-black/30 border border-[#334155] rounded-[8px] text-[#e0e0e0] text-[0.95rem] font-[inherit] resize-y leading-relaxed focus:outline-none focus:border-[#3498db] placeholder:text-[#475569]"
          placeholder={'请描述您的研究问题，包括：\n1. 研究背景与目标\n2. 具体要求（优化/预测/评价/分类/仿真等）\n3. 数据情况（如有数据文件，请先到「数据」标签上传；无数据可选"系统自动搜集"）\n4. 约束条件或特殊要求\n5. 目标投稿会议/期刊（可选，系统会自动推荐模板）'}
          value={problemText}
          onChange={e => setProblemText(e.target.value)}
          rows={10}
        />

        <div className="mt-[0.8rem] grid gap-[0.6rem] grid-cols-2">
          <div>
            <div className="text-[0.9375rem] text-[#94A3B8] font-semibold mb-2">问题类型</div>
            <select
              className="w-full p-2 bg-black/30 border border-white/15 rounded-[8px] text-[#e0e0e0] text-[0.9rem]"
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
          {currentTemplate?.domain !== 'research_survey' && (
            <div>
              <div className="text-[0.9375rem] text-[#94A3B8] font-semibold mb-2">数据来源</div>
              <select
                className="w-full p-2 bg-black/30 border border-white/15 rounded-[8px] text-[#e0e0e0] text-[0.9rem]"
                value={dataSource}
                onChange={e => setDataSource(e.target.value as any)}
              >
                <option value="upload">我会上传数据</option>
                <option value="self_collect">无数据，让系统自己搜集</option>
                <option value="upload_and_collect">我上传数据，系统再补全</option>
              </select>
            </div>
          )}
        </div>

        {dataSource !== 'self_collect' && currentTemplate?.domain !== 'research_survey' && (
          <div className="mt-2 text-[#aaa] text-[0.8rem]">
            已勾选 {selectedFiles.size} 个数据文件（请到「数据」标签上传并勾选）
          </div>
        )}
      </div>

      <div className="bg-[#1E293B] border border-[#334155] rounded-[14px] p-[1.2rem]">
        <div className="text-[1rem] text-[#F8FAFC] font-semibold mb-[0.8rem]">⚙️ 工作流与模板</div>

        <div className="mb-4">
          <div className="text-[0.9375rem] text-[#94A3B8] font-semibold mb-2">
            工作流模式（已由所选模板自动绑定：{currentWorkflowName}）
          </div>
          <div className="p-[0.75rem] bg-[rgba(37,99,235,0.1)] border border-[rgba(37,99,235,0.3)] rounded-[8px] text-[#93c5fd] text-[0.85rem]">
            {currentTemplate
              ? `「${currentTemplate.name}」模板采用「${currentWorkflowName}」工作流：${WORKFLOWS.find((w) => w.id === workflow)?.desc}`
              : `当前工作流：${currentWorkflowName}`}
          </div>
        </div>

        <div className="mb-4">
          <div className="text-[0.9375rem] text-[#94A3B8] font-semibold mb-2">论文模板（{TEMPLATES.length} 选 1）</div>
          <TemplateSelector
            value={template}
            onChange={(t) => {
              setTemplate(t);
              const tpl = TEMPLATE_OPTIONS.find((x) => x.id === t);
              if (tpl) {
                setWorkflow(tpl.defaultWorkflow);
                if (tpl.defaultWorkflow === 'deep_research') {
                  setDataSource('self_collect');
                }
              }
            }}
            disabled={submitting}
          />
        </div>

        <div className="mb-4">
          <label className="flex items-center gap-[0.6rem] cursor-pointer">
            <input type="checkbox" checked={useCritique} onChange={e => setUseCritique(e.target.checked)} className="hidden peer" />
            <span className={cn(
              'w-[36px] h-[20px] rounded-[10px] relative transition-colors duration-200 shrink-0',
              useCritique ? 'bg-[rgba(74,222,128,0.15)]' : 'bg-[#334155]'
            )}>
              <span className={cn(
                'w-4 h-4 bg-white rounded-full absolute top-[2px] left-[2px] transition-transform duration-200',
                useCritique && 'translate-x-4'
              )} />
            </span>
            <span className="text-[0.9375rem] text-[#CBD5E1]">启用自评质量循环（Writer 自评 + 自动重写，推荐开启）</span>
          </label>
        </div>
      </div>

      {isRunning && (
        <div className="bg-black/20 rounded-[8px] py-[0.8rem] px-4">
          <div className="h-[6px] bg-[#334155] rounded-[3px] overflow-hidden mb-[0.4rem]">
            <div className="h-full bg-gradient-to-r from-[#3498db] to-[#2ecc71] rounded-[3px] transition-[width] duration-300 ease-in-out" style={{ width: progress + '%' }} />
          </div>
          <div className="text-[0.875rem] text-[#3498db] font-semibold text-center">{progress}% · 生成中...</div>
        </div>
      )}

      <div className="flex gap-[0.8rem]">
        <button className="flex-1 py-[0.9rem] px-8 bg-[#2DD4BF] text-[#F8FAFC] border-none rounded-[10px] text-[1rem] font-semibold cursor-pointer hover:-translate-y-[0.5px] transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed" onClick={handleSubmit} disabled={submitting || !problemText.trim() || isRunning}>
          {submitting ? '🚀 启动中...' : isRunning ? `🔄 生成中 ${progress}%` : '🚀 启动 LabAgent 生成'}
        </button>
      </div>
    </div>
  );
}
