'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import styles from './page.module.css';

import SystemStatus from './components/SystemStatus';
import ProblemInput from './components/ProblemInput';
import AgentChat from './components/AgentChat';
import FileManager from './components/FileManager';
import TaskHistory from './components/TaskHistory';

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
  const [tab, setTab] = useState<'dashboard' | 'generate' | 'files' | 'history' | 'settings'>('dashboard');

  // Task state
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string>('idle');
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [eventSource, setEventSource] = useState<EventSource | null>(null);

  // Pause/Resume
  const [paused, setPaused] = useState(false);
  const [resuming, setResuming] = useState(false);

  // Submitting
  const [submitting, setSubmitting] = useState(false);

  // Settings
  const [settingsMsg, setSettingsMsg] = useState('');

  // ========== 提交任务 ==========
  const handleSubmit = async (params: {
    problemText: string;
    workflow: string;
    template: string;
    mode: string;
    useCritique: boolean;
  }) => {
    setSubmitting(true);
    try {
      const res = await fetch(apiBase() + '/tasks/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          problem_text: params.problemText,
          mode: params.mode,
          options: {
            workflow: params.workflow,
            template: params.template,
            use_critique: params.useCritique,
          },
        }),
      });
      const data = await res.json();
      setTaskId(data.task_id);
      setTaskStatus('running');
      setProgress(0);
      setCurrentStep('等待启动');
      setMessages([]);
      setPaused(false);
      setTab('generate');
      startSSE(data.task_id);
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

  // ========== 保存设置 ==========
  const handleSaveSettings = async () => {
    const input = document.getElementById('apiKeyInput') as HTMLInputElement;
    if (!input?.value.trim()) {
      setSettingsMsg('请输入 API 密钥');
      return;
    }
    try {
      const res = await fetch(apiBase() + '/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minimax_api_key: input.value.trim() }),
      });
      const data = await res.json();
      setSettingsMsg(data.success ? '✓ API密钥保存成功！' : '保存失败');
    } catch {
      setSettingsMsg('保存失败，请检查后端连接');
    }
  };

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <span className={styles.headerTitle}>数学建模论文全自动生成系统 v2.1</span>
        <p className={styles.subtitle}>Multi-Agent 协作 · 算法智能推荐 · 分段生成 · 显式记忆池</p>
      </header>

      <nav className={styles.nav}>
        {([
          { id: 'dashboard', label: '🏠 首页', desc: '快速开始' },
          { id: 'generate', label: '🚀 生成', desc: taskStatus === 'running' ? `进行中 ${progress}%` : '实时进度' },
          { id: 'files', label: '📁 数据', desc: '文件管理' },
          { id: 'history', label: '📋 历史', desc: '任务记录' },
          { id: 'settings', label: '⚙️ 设置', desc: '系统配置' },
        ] as const).map((t) => (
          <button
            key={t.id}
            className={`${styles.navItem} ${tab === t.id ? styles.navItemActive : ''}`}
            onClick={() => setTab(t.id)}
          >
            <span className={styles.navLabel}>{t.label}</span>
            <span className={styles.navDesc}>{t.desc}</span>
            {t.id === 'generate' && (taskStatus === 'running' || taskStatus === 'phase1' || taskStatus === 'phase2') && (
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
            <AgentChat
              messages={messages}
              taskStatus={taskStatus}
              progress={progress}
              currentStep={currentStep}
              paused={paused}
              onPause={handlePause}
              onResume={handleResume}
              resuming={resuming}
            />
          </div>
        )}

        {/* ===== 数据 ===== */}
        {tab === 'files' && (
          <FileManager taskId={taskId} />
        )}

        {/* ===== 历史 ===== */}
        {tab === 'history' && (
          <TaskHistory />
        )}

        {/* ===== 设置 ===== */}
        {tab === 'settings' && (
          <div className={styles.settingsCard}>
            <span className={styles.cardTitle}>⚙️ 系统设置</span>
            <div className={styles.settingsSection}>
              <div className={styles.settingsLabel}>MiniMax API 密钥</div>
              <div className={styles.apiKeyRow}>
                <input
                  type="password"
                  className={styles.apiKeyInput}
                  placeholder="输入 MiniMax API 密钥（必填）"
                  id="apiKeyInput"
                />
              </div>
              <div className={styles.apiKeyHint}>
                请在 <a href="https://platform.minimax.chat" target="_blank" rel="noopener" style={{ color: '#3498db' }}>MiniMax 开放平台</a> 获取密钥
              </div>
              <div className={styles.btnRow}>
                <button className={styles.submitBtn} onClick={handleSaveSettings}>💾 保存设置</button>
              </div>
              {settingsMsg && (
                <div className={styles.settingsMsg} style={{ color: settingsMsg.includes('✓') ? '#2ecc71' : '#e74c3c' }}>
                  {settingsMsg}
                </div>
              )}
            </div>
            <div className={styles.divider} />
            <div className={styles.noteBox}>
              <strong>📍 访问地址：</strong>
              <code>本机: http://localhost:3000</code><br />
              <code>局域网: 请使用本机 IP:3000</code><br />
              <strong>📖 后端 API 文档：</strong>
              <code>http://localhost:8000/docs</code>
            </div>
          </div>
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
