'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import styles from './page.module.css';

import SystemStatus from './components/SystemStatus';
import ProblemInput from './components/ProblemInput';
import AgentChat from './components/AgentChat';
import FileManager from './components/FileManager';
import TaskHistory from './components/TaskHistory';
import WorkflowManager from './components/WorkflowManager';
import AgentManager from './components/AgentManager';
import SettingsPage from './components/SettingsPage';
import PdfManager from './components/PdfManager';
import MemoryManager from './components/MemoryManager';
import EnvironmentManager from './components/EnvironmentManager';
import { useAppStore } from './store/useAppStore';
import { useTaskState } from './hooks/useTaskState';
import { TaskStatusBadge } from './components/TaskStatusBadge';
import { CameraReadyPanel } from './components/CameraReadyPanel';
import { PreFlightPanel, PreflightReport } from './components/PreFlightPanel';

declare global {
  interface Window {
    __API_BASE__?: string;
  }
}

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

/* =============================================================
 * 导航分组（侧边栏用）
 * ============================================================= */
type NavId =
  | 'dashboard' | 'generate' | 'files' | 'pdf' | 'history'
  | 'agents' | 'workflows' | 'memory' | 'environment' | 'settings';

const NAV_GROUPS: { label: string; items: { id: NavId; icon: string; label: string }[] }[] = [
  {
    label: '工作台',
    items: [
      { id: 'dashboard',  icon: '⌂', label: '首页' },
      { id: 'generate',   icon: '▶', label: '生成' },
      { id: 'history',    icon: '◷', label: '历史' },
    ],
  },
  {
    label: '资源',
    items: [
      { id: 'files',      icon: '⎙', label: '数据' },
      { id: 'pdf',        icon: '⎗', label: 'PDF' },
      { id: 'memory',     icon: '◐', label: '记忆' },
    ],
  },
  {
    label: '系统',
    items: [
      { id: 'agents',     icon: '◉', label: 'Agent' },
      { id: 'workflows',  icon: '↻', label: '流程' },
      { id: 'environment',icon: '⎈', label: '环境' },
      { id: 'settings',   icon: '⚙', label: '设置' },
    ],
  },
];

interface Message {
  id: string;
  sender: string;
  sender_label: string;
  content: string;
  type: string;
  timestamp: string;
}

export default function Home() {
  const [tab, setTab] = useState<'dashboard' | 'generate' | 'files' | 'pdf' | 'history' | 'agents' | 'workflows' | 'memory' | 'environment' | 'settings'>('dashboard');

  // Task state
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string>('idle');
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [eventSource, setEventSource] = useState<EventSource | null>(null);
  // Phase 6 (A3): useTaskState hook 接管后端 9 阶段状态机。
  // 保留旧 state 变量以兼容旧 setTaskStatus 调用；hook 通过 sync effect 同步。
  const taskState = useTaskState({ taskId });

  // 同步 hook → 旧 state（避免破坏旧组件依赖）
  useEffect(() => {
    if (taskState.state) {
      setTaskStatus(taskState.state.name);
      setProgress(taskState.state.progressPercentage);
      setCurrentStep(taskState.state.currentStep);
    }
  }, [taskState.state]);

  // Pause/Resume
  const [paused, setPaused] = useState(false);
  const [resuming, setResuming] = useState(false);

  const [cancelling, setCancelling] = useState(false);

  // Phase workflow
  const [phase, setPhase] = useState<'idle' | 'phase1' | 'phase2_confirm' | 'phase2'>('idle');
  const [subProblems, setSubProblems] = useState<string[]>([]);
  const [solveMode, setSolveMode] = useState<'batch' | 'sequential'>('batch');
  const [workflowType, setWorkflowType] = useState<string>('standard');

  // Submitting
  const [submitting, setSubmitting] = useState(false);

  // Preflight report
  const [preflightReport, setPreflightReport] = useState<PreflightReport | null>(null);

  const selectedFiles = useAppStore((s) => s.selectedFiles);
  const activeProjectId = useAppStore((s) => s.activeProjectId);
  const addTaskToProject = useAppStore((s) => s.addTaskToProject);

  const handleSubmit = async (params: {
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
  }) => {
    setSubmitting(true);
    try {
      const res = await fetch(apiBase() + '/tasks/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          problem_text: params.problemText,
          project_name: params.projectName,
          mode: params.mode,
          options: {
            workflow: params.workflow,
            template: params.template,
            use_critique: params.useCritique,
          },
          data_files: params.dataFiles,
          knowledge_base_id: params.knowledgeBaseId || undefined,
          data_source: params.dataSource,
          problem_type: params.problemType,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        // 422: 数据不匹配或缺少数据，展示 preflight 报告供用户参考
        if (res.status === 422 && data.detail?.preflight_report) {
          setPreflightReport(data.detail.preflight_report);
          alert(data.detail?.message || '数据与题目不匹配，请检查后重新提交');
          return;
        }
        alert(data.detail?.message || `提交失败: ${res.status}`);
        return;
      }
      // 成功提交：如果有 preflight_report 就展示
      if (data.preflight_report) {
        setPreflightReport(data.preflight_report);
      }
      const newTaskId = data.task_id;
      setTaskId(newTaskId);
      setTaskStatus('running');
      setProgress(0);
      setCurrentStep('等待启动');
      setMessages([]);
      setPaused(false);
      setPhase('idle');
      setWorkflowType(params.workflow);
      setTab('generate');
      if (activeProjectId && newTaskId) {
        addTaskToProject(activeProjectId, newTaskId);
      }
      startSSE(newTaskId);
    } catch (err) {
      console.error(err);
      alert('提交失败，请确认后端已启动');
    } finally {
      setSubmitting(false);
    }
  };

  // ========== SSE 流 ==========
  const startSSE = (id: string) => {
    if (eventSource) eventSource.close();
    const es = new EventSource(apiBase() + '/tasks/' + id + '/stream');
    setEventSource(es);

    const msgPoll = setInterval(async () => {
      try {
        const res = await fetch(apiBase() + '/tasks/' + id + '/messages');
        if (res.ok) {
          const msgs = await res.json();
          setMessages(
            msgs.map((m: any) => ({
              id: m.id,
              sender: m.sender,
              sender_label: m.sender_label || getTeamLabel(m.sender) || m.sender,
              content: m.content,
              type: m.type || 'text',
              timestamp: m.timestamp,
            }))
          );
        }
      } catch {}
    }, 1000);

    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        setTaskStatus(d.status);
        setProgress(d.progress || 0);
        setCurrentStep(d.current_step || '');
        if (d.status === 'paused') {
          setPaused(true);
          es.close();
          clearInterval(msgPoll);
        }
        // Phase1 completed - show sub-problem confirmation
        if (d.status === 'phase1_completed') {
          setPhase('phase2_confirm');
          loadSubProblems(id);
          es.close();
          clearInterval(msgPoll);
        }
        if (['completed', 'failed', 'cancelled'].includes(d.status)) {
          es.close();
          clearInterval(msgPoll);
        }
      } catch {}
    };

    es.onerror = () => {
      es.close();
      clearInterval(msgPoll);
    };
  };

  // ========== Phase workflow ==========
  const loadSubProblems = async (id: string) => {
    try {
      const res = await fetch(apiBase() + '/tasks/' + id + '/result');
      if (res.ok) {
        const data = await res.json();
        const sp = data?.output?.analyzer_agent?.sub_problems || data?.output?.sub_problems || [];
        if (sp.length > 0) {
          setSubProblems(sp.map((s: any) => s.description || s.text || s));
        }
      }
    } catch {}
  };

  const handlePhase1 = async () => {
    if (!taskId) return;
    setSubmitting(true);
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/phase1', { method: 'POST' });
      if (res.ok) {
        setPhase('phase1');
        setTaskStatus('running');
        startSSE(taskId);
      }
    } catch { alert('启动阶段1失败'); } finally { setSubmitting(false); }
  };

  const handlePhase2 = async () => {
    if (!taskId || subProblems.length === 0) return;
    setSubmitting(true);
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/phase2', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sub_problems: subProblems, mode: solveMode }),
      });
      if (res.ok) {
        setPhase('phase2');
        setTaskStatus('running');
        startSSE(taskId);
      }
    } catch { alert('启动阶段2失败'); } finally { setSubmitting(false); }
  };

  const handleConfirmSubproblems = async () => {
    if (!taskId) return;
    setSubmitting(true);
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/confirm-subproblems', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sub_problems: subProblems }),
      });
      if (res.ok) {
        setPhase('phase2');
        setTaskStatus('running');
        startSSE(taskId);
      }
    } catch { alert('确认子问题失败'); } finally { setSubmitting(false); }
  };

  // ========== 暂停/恢复 ==========
  const handlePause = async () => {
    if (!taskId) return;
    try {
      await fetch(apiBase() + '/tasks/' + taskId + '/pause', { method: 'POST' });
      setPaused(true);
    } catch {}
  };

  const handleResume = async () => {
    if (!taskId) return;
    setResuming(true);
    try {
      await fetch(apiBase() + '/tasks/' + taskId + '/resume', { method: 'POST' });
      setPaused(false);
      startSSE(taskId);
    } catch {} finally {
      setResuming(false);
    }
  };

  const handleCancel = async () => {
    if (!taskId) return;
    if (!confirm('确定取消当前任务？')) return;
    setCancelling(true);
    try {
      await fetch(apiBase() + '/tasks/' + taskId + '/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: '用户手动取消' }),
      });
      setTaskStatus('cancelled');
    } catch {} finally {
      setCancelling(false);
    }
  };

  // ========== Edit-and-Continue ==========
  const handleEditAndContinue = async (editedData: Record<string, any>) => {
    if (!taskId) return;
    setSubmitting(true);
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/edit-and-continue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ edited_data: editedData }),
      });
      if (res.ok) {
        setPaused(false);
        startSSE(taskId);
      }
    } catch {} finally { setSubmitting(false); }
  };

  // ========== Pause data ==========
  const [pauseData, setPauseData] = useState<any>(null);

  const loadPauseData = async () => {
    if (!taskId) return;
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/pause-data');
      if (res.ok) setPauseData(await res.json());
    } catch {}
  };

  useEffect(() => {
    if (paused && taskId) loadPauseData();
  }, [paused]);

  // ========== Navigation tabs ==========
  // NAV_GROUPS 在模块顶层定义（侧边栏渲染用）

  return (
    <>
      {/* ===== 顶栏 ===== */}
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <div className={styles['brand-mark']}>M</div>
          <span className={styles['brand-name']}>MathModel Agent</span>
          <span className={styles['brand-tag']}>LangGraph · ReAct · Auto-iterate</span>
        </div>
        <div className={styles['topbar-right']}>
          {taskState.state?.peerReview && (
            <span className="pill pill-info">
              评审 {(taskState.state.peerReview.overallScore ?? 0).toFixed(1)} / 5
            </span>
          )}
          {taskId && (
            <span className={`pill ${
              taskStatus === 'completed' ? 'pill-ok' :
              taskStatus === 'failed' || taskStatus === 'interrupted' ? 'pill-err' :
              ['running', 'phase1_running', 'phase2_running'].includes(taskStatus) ? 'pill-info' :
              'pill-muted'
            }`}>
              {taskStatus}
            </span>
          )}
          <span className={styles['topbar-version']}>v2.1.0</span>
        </div>
      </header>

      <div className={styles.layout}>
        {/* ===== 左侧导航 ===== */}
        <aside className={styles.sidebar}>
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className={styles['nav-section']}>
              <div className={styles['nav-section-title']}>{group.label}</div>
              {group.items.map((t) => (
                <button
                  key={t.id}
                  className={styles['nav-item']}
                  data-active={tab === t.id}
                  onClick={() => setTab(t.id)}
                >
                  <span className={styles['nav-icon']}>{t.icon}</span>
                  <span>{t.label}</span>
                </button>
              ))}
            </div>
          ))}
        </aside>

        {/* ===== 主内容区 ===== */}
        <main className={styles.content}>
          {tab === 'dashboard' && (
            <div>
              <SystemStatus />
              <ProblemInput
                onSubmit={handleSubmit}
                submitting={submitting}
                taskStatus={taskStatus}
                progress={progress}
              />
            </div>
          )}

          {tab === 'generate' && (
            <div>
              {(phase === 'idle' && taskId && taskStatus !== 'running' && taskStatus !== 'completed') && (
                <div className="banner banner-info" style={{ marginTop: 16 }}>
                  <div style={{ flex: 1 }}>
                    <div className="banner-title">分阶段工作流</div>
                    <div className="banner-desc">阶段1完成后可确认子问题列表，再启动阶段2建模求解</div>
                  </div>
                  <button className="btn btn-primary" onClick={handlePhase1}>
                    🔄 启动阶段1
                  </button>
                </div>
              )}

              {phase === 'phase2_confirm' && (
                <div className="banner banner-ok" style={{ marginTop: 16, flexDirection: 'column', alignItems: 'stretch' }}>
                  <div className="banner-title">✅ 阶段1已完成</div>
                  <div className="banner-desc" style={{ marginBottom: 12 }}>确认子问题后启动阶段2</div>
                  <div className="section-title" style={{ marginBottom: 8 }}>子问题列表（可编辑）</div>
                  {subProblems.map((sp, idx) => (
                    <div key={idx} className="flex gap-2 items-center" style={{ marginBottom: 8 }}>
                      <span className="text-muted text-sm" style={{ width: 24 }}>{idx + 1}.</span>
                      <input
                        className="input"
                        value={sp}
                        onChange={e => {
                          const next = [...subProblems];
                          next[idx] = e.target.value;
                          setSubProblems(next);
                        }}
                      />
                      <button className="btn btn-danger btn-sm" onClick={() => setSubProblems(subProblems.filter((_, i) => i !== idx))}>
                        删除
                      </button>
                    </div>
                  ))}
                  <button className="btn btn-ghost btn-sm" onClick={() => setSubProblems([...subProblems, ''])}>
                    + 添加子问题
                  </button>

                  <div className="divider"></div>

                  <div className="section-title" style={{ marginBottom: 8 }}>求解策略</div>
                  <div className="flex gap-2">
                    <label className="flex items-center gap-1" style={{ cursor: 'pointer' }}>
                      <input type="radio" checked={solveMode === 'sequential'} onChange={() => setSolveMode('sequential')} />
                      <span>逐个递进</span>
                    </label>
                    <label className="flex items-center gap-1" style={{ cursor: 'pointer' }}>
                      <input type="radio" checked={solveMode === 'batch'} onChange={() => setSolveMode('batch')} />
                      <span>批量并行</span>
                    </label>
                  </div>

                  <div className="flex gap-2" style={{ marginTop: 16 }}>
                  <button onClick={handleConfirmSubproblems} style={{ padding: '0.5rem 1rem', background: 'linear-gradient(135deg, #2ecc71, #27ae60)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }} disabled={submitting}>
                    {submitting ? '启动中...' : '✅ 确认子问题并启动阶段2'}
                  </button>
                  <button onClick={handlePhase2} style={{ padding: '0.5rem 1rem', background: 'linear-gradient(135deg, #3498db, #2980b9)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }} disabled={submitting}>
                    {submitting ? '启动中...' : '🚀 直接启动阶段2'}
                  </button>
                </div>
              </div>
            )}

            {/* Pause data editor */}
            {paused && pauseData && (
              <div style={{ background: 'rgba(243,156,18,0.08)', border: '1px solid rgba(243,156,18,0.2)', borderRadius: 10, padding: '1rem' }}>
                <span style={{ color: '#f39c12', fontWeight: 600, fontSize: '1rem', display: 'block', marginBottom: '0.8rem' }}>
                  ⏸ 任务已暂停 — 可编辑 Agent 输出后继续
                </span>
                <div style={{ color: '#888', fontSize: '0.8rem', marginBottom: '0.5rem' }}>
                  暂停位置: {pauseData?.pause_location || '未知'}
                </div>
                {Object.entries(pauseData?.pause_data || {}).map(([key, value]) => (
                  <div key={key} style={{ marginBottom: '0.8rem' }}>
                    <div style={{ color: '#ddd', fontSize: '0.85rem', marginBottom: '0.3rem' }}>{key}</div>
                    <textarea
                      defaultValue={typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
                      id={`pause_edit_${key}`}
                      style={{ width: '100%', padding: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.85rem', minHeight: 100, fontFamily: 'monospace' }}
                    />
                  </div>
                ))}
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button onClick={() => {
                    const edited: Record<string, any> = {};
                    Object.keys(pauseData?.pause_data || {}).forEach(key => {
                      const el = document.getElementById(`pause_edit_${key}`) as HTMLTextAreaElement;
                      if (el) {
                        try { edited[key] = JSON.parse(el.value); } catch { edited[key] = el.value; }
                      }
                    });
                    handleEditAndContinue(edited);
                  }} style={{ padding: '0.5rem 1rem', background: 'linear-gradient(135deg, #2ecc71, #27ae60)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }} disabled={submitting}>
                    {submitting ? '提交中...' : '✅ 应用编辑并继续'}
                  </button>
                  <button onClick={handleResume} style={{ padding: '0.5rem 1rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 8, color: '#3498db', cursor: 'pointer' }} disabled={resuming}>
                    {resuming ? '继续中...' : '▶ 不编辑，直接继续'}
                  </button>
                </div>
              </div>
            )}

            {/* Preflight 预检报告 */}
            {preflightReport && (
              <PreFlightPanel
                report={preflightReport}
                onConfirm={() => setPreflightReport(null)}
              />
            )}

            {/* Phase 6 (A3): 任务状态机可视化 */}
            {taskState.state && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: '0.8rem', flexWrap: 'wrap' }}>
                <TaskStatusBadge
                  state={taskState.state.name}
                  progressPercentage={taskState.state.progressPercentage}
                />
                {taskState.state.currentStep && (
                  <span style={{ color: '#aaa', fontSize: '0.85rem' }}>
                    {taskState.state.currentStep}
                  </span>
                )}
              </div>
            )}

            <AgentChat
              messages={messages}
              taskStatus={taskStatus}
              progress={progress}
              currentStep={currentStep}
              workflowType={workflowType}
              paused={paused}
              onPause={handlePause}
              onResume={handleResume}
              onCancel={handleCancel}
              resuming={resuming}
              cancelling={cancelling}
              taskId={taskId}
            />

            {/* Phase 6 (A3): 完成后 Camera-Ready 打包 */}
            {taskState.state?.name === 'completed' && taskId && (
              <div style={{ marginTop: '1rem' }}>
                <CameraReadyPanel
                  taskId={taskId}
                  templateId={taskState.state?.templateId || 'math_modeling'}
                />
              </div>
            )}
          </div>
        )}

        {/* ===== 数据 ===== */}
        {tab === 'files' && (
          <FileManager taskId={taskId} />
        )}

        {/* ===== PDF ===== */}
        {tab === 'pdf' && (
          <PdfManager />
        )}

        {/* ===== 历史 ===== */}
        {tab === 'history' && (
          <TaskHistory />
        )}

        {/* ===== Agent管理 ===== */}
        {tab === 'agents' && (
          <AgentManager />
        )}

        {/* ===== 工作流 ===== */}
        {tab === 'workflows' && (
          <WorkflowManager />
        )}

        {/* ===== 记忆 ===== */}
        {tab === 'memory' && (
          <MemoryManager />
        )}

        {/* ===== 环境管理 ===== */}
        {tab === 'environment' && (
          <EnvironmentManager />
        )}

        {/* ===== 设置（包含 Provider/MCP/知识库/系统 子标签） ===== */}
        {tab === 'settings' && (
          <SettingsPage />
        )}
        </main>
      </div>
    </>
  );
}

function getTeamLabel(sender: string): string {
  const labels: Record<string, string> = {
    coordinator: '协调者',
    research_agent: '研究员',
    data_agent: '数据分析师',
    analyzer_agent: '分析师',
    modeler_agent: '建模师',
    algorithm_engineer_agent: '算法工程师',
    financial_analyst_agent: '金融分析师',
    solver_agent: '求解器',
    writer_agent: '写作专家',
    peer_review_agent: '审稿人',
    experimentation_agent: '实验设计专家',
    figure_agent: '科研绘图师',
    system: '系统',
    user: '你',
  };
  return labels[sender] || sender;
}