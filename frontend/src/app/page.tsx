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
import { useAppStore } from './store/useAppStore';
import { useTaskState } from './hooks/useTaskState';
import { TaskStatusBadge } from './components/TaskStatusBadge';
import { CameraReadyPanel } from './components/CameraReadyPanel';

declare global {
  interface Window {
    __API_BASE__?: string;
  }
}

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

interface Message {
  id: string;
  sender: string;
  sender_label: string;
  content: string;
  type: string;
  timestamp: string;
}

export default function Home() {
  const [tab, setTab] = useState<'dashboard' | 'generate' | 'files' | 'pdf' | 'history' | 'agents' | 'workflows' | 'memory' | 'settings'>('dashboard');

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

  // Submitting
  const [submitting, setSubmitting] = useState(false);

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
        alert(data.detail?.message || `提交失败: ${res.status}`);
        return;
      }
      const newTaskId = data.task_id;
      setTaskId(newTaskId);
      setTaskStatus('running');
      setProgress(0);
      setCurrentStep('等待启动');
      setMessages([]);
      setPaused(false);
      setPhase('idle');
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
  const navItems = [
    { id: 'dashboard', label: '🏠 首页', desc: '快速开始' },
    { id: 'generate', label: '🚀 生成', desc: taskStatus === 'running' || taskStatus === 'phase1' || taskStatus === 'phase2' ? `进行中 ${progress}%` : '实时进度' },
    { id: 'files', label: '📁 数据', desc: '文件管理' },
    { id: 'pdf', label: '📄 PDF', desc: '解析/下载' },
    { id: 'history', label: '📋 历史', desc: '任务记录' },
    { id: 'agents', label: '🤖 Agent', desc: '团队管理' },
    { id: 'workflows', label: '🔄 流程', desc: '工作流' },
    { id: 'memory', label: '🧠 记忆', desc: '经验教训/任务记忆' },
    { id: 'settings', label: '⚙️ 设置', desc: 'Provider/MCP/知识库/系统' },
  ] as const;

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <span className={styles.headerTitle}>数学建模论文全自动生成系统 v3.0</span>
        <p className={styles.subtitle}>Multi-Agent 协作 · 多LLM Provider · MCP工具 · 分阶段交互 · 显式记忆池</p>
      </header>

      <nav className={styles.nav}>
        {navItems.map((t) => (
          <button
            key={t.id}
            className={`${styles.navItem} ${tab === t.id ? styles.navItemActive : ''}`}
            onClick={() => setTab(t.id)}
          >
            <span className={styles.navLabel}>{t.label}</span>
            <span className={styles.navDesc}>{t.desc}</span>
            {(t.id === 'generate') && (taskStatus === 'running' || taskStatus === 'phase1' || taskStatus === 'phase2') && (
              <span className={styles.navDot} />
            )}
          </button>
        ))}
      </nav>

      <div className={styles.container}>
        {/* ===== 首页 ===== */}
        {tab === 'dashboard' && (
          <div className={styles.dashboard}>
            <SystemStatus />
            <ProblemInput
              onSubmit={handleSubmit}
              submitting={submitting}
              taskStatus={taskStatus}
              progress={progress}
            />
          </div>
        )}

        {/* ===== 生成 ===== */}
        {tab === 'generate' && (
          <div className={styles.generateLayout}>
            {/* Phase1/Phase2 controls */}
            {(phase === 'idle' && taskId && taskStatus !== 'running' && taskStatus !== 'completed') && (
              <div style={{ background: 'rgba(52,152,219,0.08)', border: '1px solid rgba(52,152,219,0.2)', borderRadius: 10, padding: '1rem' }}>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span style={{ color: '#3498db', fontWeight: 600 }}>分阶段工作流</span>
                  <button onClick={handlePhase1} style={{ padding: '0.4rem 0.8rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 6, color: '#3498db', fontSize: '0.78rem', cursor: 'pointer' }}>
                    🔄 启动阶段1（分析+数据）
                  </button>
                </div>
                <div style={{ color: '#888', fontSize: '0.8rem', marginTop: '0.3rem' }}>阶段1完成后可确认子问题列表，再启动阶段2建模求解</div>
              </div>
            )}

            {/* Phase2 sub-problem confirmation */}
            {phase === 'phase2_confirm' && (
              <div style={{ background: 'rgba(46,204,113,0.08)', border: '1px solid rgba(46,204,113,0.2)', borderRadius: 10, padding: '1rem' }}>
                <span style={{ color: '#2ecc71', fontWeight: 600, fontSize: '1rem', display: 'block', marginBottom: '0.8rem' }}>
                  ✅ 阶段1已完成 — 确认子问题后启动阶段2
                </span>
                <div style={{ marginBottom: '0.8rem' }}>
                  <div style={{ color: '#ddd', fontSize: '0.85rem', marginBottom: '0.5rem' }}>子问题列表（可编辑）：</div>
                  {subProblems.map((sp, idx) => (
                    <div key={idx} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.4rem' }}>
                      <span style={{ color: '#f39c12', fontSize: '0.85rem', minWidth: 20 }}>{idx + 1}.</span>
                      <input
                        value={sp}
                        onChange={e => {
                          const next = [...subProblems];
                          next[idx] = e.target.value;
                          setSubProblems(next);
                        }}
                        style={{ flex: 1, padding: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }}
                      />
                      <button onClick={() => setSubProblems(subProblems.filter((_, i) => i !== idx))} style={{ padding: '0.3rem 0.5rem', background: 'rgba(231,76,60,0.15)', border: '1px solid rgba(231,76,60,0.3)', borderRadius: 6, color: '#e74c3c', fontSize: '0.75rem', cursor: 'pointer' }}>✕</button>
                    </div>
                  ))}
                  <button onClick={() => setSubProblems([...subProblems, ''])} style={{ padding: '0.3rem 0.6rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 6, color: '#3498db', fontSize: '0.75rem', cursor: 'pointer', marginTop: '0.3rem' }}>+ 添加子问题</button>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.8rem' }}>
                  <span style={{ color: '#ddd', fontSize: '0.85rem' }}>求解策略：</span>
                  <label style={{ display: 'flex', gap: '0.3rem', alignItems: 'center', cursor: 'pointer' }}>
                    <input type="radio" checked={solveMode === 'sequential'} onChange={() => setSolveMode('sequential')} />
                    <span style={{ color: '#aaa', fontSize: '0.85rem' }}>逐个递进</span>
                  </label>
                  <label style={{ display: 'flex', gap: '0.3rem', alignItems: 'center', cursor: 'pointer' }}>
                    <input type="radio" checked={solveMode === 'batch'} onChange={() => setSolveMode('batch')} />
                    <span style={{ color: '#aaa', fontSize: '0.85rem' }}>批量并行</span>
                  </label>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
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
              paused={paused}
              onPause={handlePause}
              onResume={handleResume}
              onCancel={handleCancel}
              resuming={resuming}
              cancelling={cancelling}
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

        {/* ===== 设置（包含 Provider/MCP/知识库/系统 子标签） ===== */}
        {tab === 'settings' && (
          <SettingsPage />
        )}
      </div>
    </main>
  );
}

function getTeamLabel(sender: string): string {
  const labels: Record<string, string> = {
    coordinator: '协调者',
    research_agent: '研究员',
    data_agent: '数据分析师',
    analyzer_agent: '分析师',
    modeler_agent: '建模师',
    solver_agent: '求解器',
    writer_agent: '写作专家',
    system: '系统',
    user: '你',
  };
  return labels[sender] || sender;
}