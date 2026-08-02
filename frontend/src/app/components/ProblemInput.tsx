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

// localStorage 草稿键：页面刷新/误关后恢复未提交的表单输入
export const DRAFT_KEY = 'labagent:generate:draft:v1';

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
  const toggleFile = useAppStore((s) => s.toggleFileSelection);
  const selectAllFiles = useAppStore((s) => s.selectAllFiles);
  const clearFileSelection = useAppStore((s) => s.clearFileSelection);
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

  // 挂载时恢复草稿（仅恢复有内容的字段）
  useEffect(() => {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (!raw) return;
      const d = JSON.parse(raw);
      if (d.problemText) setProblemText(d.problemText);
      if (d.workflow) setWorkflow(d.workflow);
      if (d.template) setTemplate(d.template);
      if (d.dataSource) setDataSource(d.dataSource);
      if (d.problemType) setProblemType(d.problemType);
      if (typeof d.useCritique === 'boolean') setUseCritique(d.useCritique);
    } catch {
      // 草稿损坏则忽略
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 防抖 800ms 自动保存草稿（刷新/切页不丢输入）
  useEffect(() => {
    const t = setTimeout(() => {
      try {
        localStorage.setItem(DRAFT_KEY, JSON.stringify({
          problemText, workflow, template, dataSource, problemType, useCritique,
        }));
      } catch {
        // 存储不可用则忽略
      }
    }, 800);
    return () => clearTimeout(t);
  }, [problemText, workflow, template, dataSource, problemType, useCritique]);

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

  // 数据文件预览+选择
  const [availableFiles, setAvailableFiles] = useState<Array<{name: string; size: number; type: string; source?: string; modified?: number}>>([])
  const [expandedFile, setExpandedFile] = useState<string | null>(null)
  const [previewCache, setPreviewCache] = useState<Record<string, any>>({})
  const [filesLoading, setFilesLoading] = useState(false)
  useEffect(() => {
    let cancelled = false
    async function loadFiles() {
      setFilesLoading(true)
      try {
        const params = new URLSearchParams()
        if (projectName) params.set('project_name', projectName)
        params.set('source', 'both')
        const res = await fetch(apiBase() + '/data/files?' + params.toString())
        if (res.ok && !cancelled) {
          const list: any[] = await res.json()
          // 过滤掉非表格文件但保留PDF/image? 不,全部列,预览时会显示unsupported
          const filtered = list.filter((f: any) => !f.name.startsWith('.'))
          setAvailableFiles(filtered)
          // 默认全选：selectAll(names) 替换为传入的文件名集合
          selectAllFiles(filtered.map((f: any) => f.name))
        }
      } catch {} finally { if (!cancelled) setFilesLoading(false) }
    }
    loadFiles()
    return () => { cancelled = true }
  }, [projectName])

  async function toggleExpandPreview(name: string) {
    if (expandedFile === name) { setExpandedFile(null); return }
    setExpandedFile(name)
    if (previewCache[name]) return
    try {
      const params = new URLSearchParams()
      params.set('filename', name)
      if (projectName) params.set('project_name', projectName)
      const res = await fetch(apiBase() + '/data/preview?' + params.toString())
      if (res.ok) {
        const data = await res.json()
        setPreviewCache(prev => ({...prev, [name]: data}))
      }
    } catch {}
  }

  const currentTemplate = TEMPLATE_OPTIONS.find((t) => t.id === template);
  const currentWorkflowName = WORKFLOWS.find((w) => w.id === workflow)?.name || workflow;

  return (
    <div data-design-id="generate:root" className="flex flex-col gap-4 mx-auto w-full max-w-[1320px]">
      <div data-design-id="generate:card-input" className="bg-card border border-border rounded-xl px-7 py-5 w-full">
        <div data-design-id="generate:title-input" className="text-lg text-foreground font-semibold mb-3">📝 研究问题输入</div>
        <div className="flex gap-3 items-center mb-2">
          <select
            className="flex-1 px-4 py-2 bg-muted border border-border rounded-md text-foreground text-sm"
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
              className="py-1.5 px-5 bg-error/10 border border-error/20 rounded-md text-error cursor-pointer text-sm transition-colors hover:bg-error/15"
            >
              🗑️ 删除
            </button>
          )}
          {showNewProject && (
            <div className="flex gap-3 items-center">
              <input
                className="px-4 py-2 bg-muted border border-border rounded-md text-foreground text-sm w-36"
                placeholder="项目名称"
                value={newProjectName}
                onChange={e => setNewProjectName(e.target.value)}
                maxLength={60}
              />
              <button onClick={handleCreateProject} className="py-1.5 px-5 bg-primary text-primary-foreground border-none rounded-md cursor-pointer text-sm transition-opacity hover:opacity-90">创建</button>
              <button onClick={() => setShowNewProject(false)} className="py-1.5 px-5 bg-error/10 border border-error/20 rounded-md text-error cursor-pointer text-sm transition-colors hover:bg-error/15">取消</button>
            </div>
          )}
        </div>
        <input
          data-design-id="generate:input-project"
          className="w-full py-3 px-6 mb-2.5 bg-muted border border-border rounded-md text-foreground text-sm"
          placeholder="输入项目名称（如：供应链优化 / CCF-A 论文 / 金融风控模型）"
          value={projectName}
          onChange={e => setProjectName(e.target.value)}
          maxLength={60}
        />
        <div className="mt-2">
          <div className="flex gap-3 items-center mb-1.5">
            <span className="text-muted-foreground text-sm">
              📚 关联知识库（v5.4.0：可多选）
            </span>
            {selectedKBIds.size > 0 && (
              <button
                type="button"
                onClick={clearKBSelection}
                className="py-0.5 px-5 bg-transparent text-muted-foreground border border-border rounded-md text-xs cursor-pointer"
              >
                清空
              </button>
            )}
          </div>
          {knowledgeBases.length === 0 ? (
            <div className="px-4 py-2 text-muted-foreground text-sm italic">
              暂无知识库；留空将自动使用项目私有 + 全局公共 KB
            </div>
          ) : (
            <div data-design-id="generate:row-kb" className="flex flex-wrap gap-3">
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
                      'py-1.5 px-5 border rounded-2xl cursor-pointer text-sm transition-colors duration-150',
                      selected
                        ? 'bg-primary text-primary-foreground border-primary font-semibold'
                        : 'bg-muted text-muted-foreground border-border font-normal hover:border-foreground/20'
                    )}
                  >
                    {isProject ? '📁' : '🌐'} {kb.name}
                    {selected && ' ✓'}
                  </button>
                );
              })}
            </div>
          )}
          <div className="mt-1.5 text-muted-foreground text-xs">
            不选 = 自动注入「项目私有 + 全局公共」KB；勾选 = 仅使用勾选的 KB
          </div>
        </div>
        <div className="flex items-center gap-4 mb-3">
          <label data-design-id="generate:btn-ocr" className="inline-flex items-center gap-3 py-2.5 px-7 bg-primary text-primary-foreground rounded-md cursor-pointer text-sm font-semibold transition-opacity duration-150 hover:opacity-90 disabled:opacity-60 disabled:cursor-not-allowed">
            {ocrLoading ? '识别中...' : '📷 上传问题图片 / PDF（OCR 提取文本）'}
            <input type="file" accept="image/*,.pdf" onChange={handleOcrUpload} className="hidden" disabled={ocrLoading} />
          </label>
          <span className="text-muted-foreground text-sm">支持 JPG / PNG / PDF，自动提取文本</span>
        </div>
        <textarea
          data-design-id="generate:input-problem"
          className="w-full px-6 py-4 bg-muted border border-border rounded-md text-foreground text-sm font-[inherit] resize-y leading-relaxed focus:outline-none focus:border-primary placeholder:text-muted-foreground"
          placeholder={'请描述您的研究问题，包括：\n1. 研究背景与目标\n2. 具体要求（优化/预测/评价/分类/仿真等）\n3. 数据情况（如有数据文件，请先到「数据」标签上传；无数据可选"系统自动搜集"）\n4. 约束条件或特殊要求\n5. 目标投稿会议/期刊（可选，系统会自动推荐模板）'}
          value={problemText}
          onChange={e => setProblemText(e.target.value)}
          rows={10}
        />

        <div className="mt-3 grid gap-2.5 grid-cols-2">
          <div>
            <div className="text-sm text-muted-foreground font-semibold mb-2">问题类型</div>
            <select
              className="w-full px-4 py-2 bg-muted border border-border rounded-md text-foreground text-sm"
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
              <div className="text-sm text-muted-foreground font-semibold mb-2">数据来源</div>
              <select
                className="w-full px-4 py-2 bg-muted border border-border rounded-md text-foreground text-sm"
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
          <div data-design-id="generate:row-files" className="mt-2 w-full">
            <div className="text-muted-foreground text-sm mb-2">
              已选 {selectedFiles.size} / {availableFiles.length} 个数据文件（点文件名展开预览，勾选框控制是否参与本次任务）
            </div>
            {filesLoading && <div className="text-xs text-muted-foreground py-2">加载数据文件中...</div>}
            {!filesLoading && availableFiles.length === 0 && (
              <div className="text-xs text-muted-foreground py-2">暂无数据文件，请先到「文件管理」上传，或选择「系统自己搜集数据」。</div>
            )}
            <div className="flex flex-col gap-2 max-h-[360px] overflow-y-auto pr-1">
              {availableFiles.map(f => {
                const checked = selectedFiles.has(f.name)
                const preview = previewCache[f.name]
                const isExpanded = expandedFile === f.name
                return (
                  <div key={f.name} className="border border-border rounded-lg bg-muted/40 overflow-hidden">
                    <div className="flex items-center gap-2 px-3 py-2">
                      <input
                        type="checkbox"
                        className="accent-primary w-4 h-4 cursor-pointer shrink-0"
                        checked={checked}
                        onChange={() => toggleFile(f.name)}
                      />
                      <button
                        type="button"
                        className="flex-1 text-left text-sm text-foreground hover:text-primary transition-colors truncate"
                        onClick={() => toggleExpandPreview(f.name)}
                        title={f.name}
                      >
                        {isExpanded ? '▼ ' : '▶ '}{f.name}
                        <span className="ml-2 text-xs text-muted-foreground">{(f.size/1024).toFixed(1)} KB · {f.type || '未知类型'}</span>
                      </button>
                    </div>
                    {isExpanded && preview && (
                      <div className="px-3 pb-3 pt-1 border-t border-border bg-background/60 text-xs">
                        {preview.preview_type === 'table' ? (
                          <>
                            <div className="text-muted-foreground mb-1">
                              {preview.columns.length} 列{preview.rows_total_estimate ? `，约 ${preview.rows_total_estimate} 行` : ''}
                            </div>
                            <div className="flex flex-wrap gap-1 mb-2">
                              {preview.columns.map((col: string) => (
                                <span key={col} className="px-2 py-0.5 bg-primary/10 text-primary rounded border border-primary/20">{col}</span>
                              ))}
                            </div>
                            {preview.preview_rows?.length > 0 && (
                              <div className="overflow-x-auto">
                                <table className="min-w-full text-xs">
                                  <thead>
                                    <tr className="border-b border-border">
                                      {preview.columns.map((col: string) => <th key={col} className="px-2 py-1 text-left text-muted-foreground font-normal">{col}</th>)}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {preview.preview_rows.map((row: any, i: number) => (
                                      <tr key={i} className="border-b border-border/50">
                                        {preview.columns.map((col: string) => <td key={col} className="px-2 py-1 text-foreground">{String(row[col] ?? '')}</td>)}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            )}
                          </>
                        ) : preview.preview_type === 'unsupported' ? (
                          <div className="text-muted-foreground">非表格文件（{preview.type}），不支持预览表头。</div>
                        ) : preview.preview_type === 'error' ? (
                          <div className="text-error">预览失败: {preview.error}</div>
                        ) : (
                          <div className="text-muted-foreground">加载中...</div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      <div data-design-id="generate:card-template" className="bg-card border border-border rounded-xl px-7 py-5 w-full">
        <div data-design-id="generate:title-template" className="text-lg text-foreground font-semibold mb-3">⚙️ 工作流与模板</div>

        <div className="mb-4">
          <div className="text-sm text-muted-foreground font-semibold mb-2">
            工作流模式（已由所选模板自动绑定：{currentWorkflowName}）
          </div>
          <div className="px-5 py-3 bg-primary/10 border border-primary/20 rounded-md text-foreground text-sm">
            {currentTemplate
              ? `「${currentTemplate.name}」模板采用「${currentWorkflowName}」工作流：${WORKFLOWS.find((w) => w.id === workflow)?.desc}`
              : `当前工作流：${currentWorkflowName}`}
          </div>
        </div>

        <div className="mb-4">
          <div className="text-sm text-muted-foreground font-semibold mb-2">论文模板（{TEMPLATES.length} 选 1）</div>
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
          <label className="flex items-center gap-2.5 cursor-pointer">
            <input type="checkbox" checked={useCritique} onChange={e => setUseCritique(e.target.checked)} className="hidden peer" />
            <span className={cn(
              'w-9 h-5 rounded-lg relative transition-colors duration-200 shrink-0',
              useCritique ? 'bg-primary' : 'bg-muted'
            )}>
              <span className={cn(
                'w-4 h-4 bg-white rounded-full absolute top-0.5 left-0.5 transition-transform duration-200',
                useCritique && 'translate-x-4'
              )} />
            </span>
            <span className="text-sm text-foreground">启用自评质量循环（Writer 自评 + 自动重写，推荐开启）</span>
          </label>
        </div>
      </div>

      {isRunning && (
        <div className="bg-muted rounded-md py-3 px-6">
          <div className="h-1.5 bg-muted rounded-sm overflow-hidden mb-1.5">
            <div className="h-full bg-primary rounded-sm transition-[width] duration-300 ease-in-out" style={{ width: progress + '%' }} />
          </div>
          <div className="text-sm text-primary font-semibold text-center">{progress}% · 生成中...</div>
        </div>
      )}

      <div className="flex gap-3">
        <button data-design-id="generate:btn-submit" className="flex-1 py-3.5 px-10 bg-primary text-primary-foreground border-none rounded-lg text-base font-semibold cursor-pointer transition-opacity duration-150 hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed" onClick={handleSubmit} disabled={submitting || !problemText.trim() || isRunning}>
          {submitting ? '🚀 启动中...' : isRunning ? `🔄 生成中 ${progress}%` : '🚀 启动 LabAgent 生成'}
        </button>
      </div>
    </div>
  );
}
