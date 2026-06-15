'use client';

import { useRef, useEffect, useState } from 'react';
import styles from './AgentChat.module.css';
import StageProgress from './StageProgress';

interface Message {
  id: string;
  sender: string;
  sender_label: string;
  content: string;
  type: string;
  timestamp: string;
}

interface AgentChatProps {
  messages: Message[];
  taskStatus: string;
  progress: number;
  currentStep?: string;
  paused: boolean;
  onPause: () => void;
  onResume: () => void;
  onCancel?: () => void;
  resuming: boolean;
  cancelling?: boolean;
  taskId?: string | null;
  onUserSend?: (content: string) => void;
}

const TEAM_COLORS: Record<string, string> = {
  coordinator: '#e74c3c',
  research_agent: '#3498db',
  data_agent: '#9b59b6',
  analyzer_agent: '#f39c12',
  modeler_agent: '#27ae60',
  solver_agent: '#e67e22',
  writer_agent: '#1abc9c',
  peer_review_agent: '#8e44ad',
  system: '#95a5a6',
  user: '#3498db',
};

const TEAM_LABELS: Record<string, string> = {
  coordinator: '协调者',
  research_agent: '研究员',
  data_agent: '数据分析师',
  analyzer_agent: '分析师',
  modeler_agent: '建模师',
  solver_agent: '求解器',
  writer_agent: '写作专家',
  peer_review_agent: '审稿人',
  system: '系统',
  user: '你',
};

function formatTime(iso: string) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString('zh-CN', { hour12: false }); } catch { return iso; }
}

type StageStatus = 'pending' | 'running' | 'completed' | 'failed';

function deriveStages(status: string, progress: number, currentStep: string) {
  const stages: { id: string; name: string; description: string; status: StageStatus; progress: number }[] = [
    { id: 'analysis', name: '问题分析', description: '数据预处理、子问题分解、文献搜集', status: 'pending', progress: 0 },
    { id: 'modeling', name: '建模求解', description: '建模、代码生成、迭代验证', status: 'pending', progress: 0 },
    { id: 'writing', name: '论文写作', description: '章节生成、自评改进、LaTeX排版', status: 'pending', progress: 0 },
    { id: 'review', name: '同行评议', description: '4维评分、修订循环、Camera-Ready打包', status: 'pending', progress: 0 },
  ];

  if (status === 'idle' || status === 'pending') return stages;

  if (status === 'phase1' || status === 'running') {
    stages[0].status = 'running';
    stages[0].progress = Math.min(progress * 2, 100);
    if (currentStep?.includes('建模') || currentStep?.includes('求解') || currentStep?.includes('model') || currentStep?.includes('solve')) {
      stages[0].status = 'completed';
      stages[0].progress = 100;
      stages[1].status = 'running';
      stages[1].progress = Math.min((progress - 30) * 2, 100);
    }
    if (currentStep?.includes('论文') || currentStep?.includes('write')) {
      stages[0].status = 'completed';
      stages[1].status = 'completed';
      stages[2].status = 'running';
      stages[2].progress = Math.min((progress - 60) * 2.5, 100);
    }
    if (currentStep?.includes('评议') || currentStep?.includes('review') || currentStep?.includes('修订')) {
      stages[0].status = 'completed';
      stages[1].status = 'completed';
      stages[2].status = 'completed';
      stages[3].status = 'running';
      stages[3].progress = Math.min((progress - 80) * 5, 100);
    }
  }

  if (status === 'completed') {
    stages.forEach(s => { s.status = 'completed'; s.progress = 100; });
  }
  if (status === 'failed') {
    stages.forEach(s => { if (s.status === 'running') s.status = 'failed'; });
  }

  return stages;
}

export default function AgentChat({
  messages, taskStatus, progress, currentStep, paused, onPause, onResume, onCancel, resuming, cancelling,
  taskId, onUserSend,
}: AgentChatProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [userInput, setUserInput] = useState('');
  const [sending, setSending] = useState(false);
  const stages = deriveStages(taskStatus, progress, currentStep || '');

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const isRunning = taskStatus === 'running' || taskStatus === 'phase1' || taskStatus === 'phase2';
  const isWaiting = currentStep?.includes('waiting') || currentStep?.includes('等待');

  const handleSend = async () => {
    const content = userInput.trim();
    if (!content || !taskId) return;
    setSending(true);
    try {
      const apiBase = () => (typeof window !== 'undefined' && (window as any).__API_BASE__) || 'http://localhost:8000/api/v1';
      await fetch(`${apiBase()}/tasks/${taskId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      setUserInput('');
      onUserSend?.(content);
    } catch (e) {
      console.error('发送消息失败:', e);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={styles.container}>
      <StageProgress stages={stages} currentStep={currentStep} />

      <div className={styles.chatCard}>
        <div className={styles.chatHeader}>
          <div className={styles.chatTitleRow}>
            <span className={styles.chatTitle}>💬 Agent 团队实时讨论</span>
            <div className={styles.teamBadges}>
              {Object.entries(TEAM_LABELS).filter(([k]) => k !== 'system').map(([k, v]) => (
                <span key={k} className={styles.badge} style={{ background: TEAM_COLORS[k] }}>{v}</span>
              ))}
            </div>
          </div>
          <div className={styles.chatActions}>
            {isRunning && !paused && (
              <>
                <button className={styles.pauseBtn} onClick={onPause}>⏸ 暂停</button>
                {onCancel && (
                  <button className={styles.cancelBtn} onClick={onCancel} disabled={cancelling}>
                    {cancelling ? '取消中...' : '⏹ 取消'}
                  </button>
                )}
              </>
            )}
            {paused && (
              <button className={styles.resumeBtn} onClick={onResume} disabled={resuming}>
                {resuming ? '继续中...' : '▶ 继续执行'}
              </button>
            )}
          </div>
        </div>

        <div className={styles.messages}>
          {messages.length === 0 && (
            <div className={styles.emptyState}>提交问题后，各 Agent 将在此展开协作讨论</div>
          )}
          {messages.map(msg => (
            <div
              key={msg.id}
              className={msg.type === 'result' ? styles.msgResult : msg.type === 'user_input' ? styles.msgUser : msg.type === 'discussion' ? styles.msgDiscuss : styles.msg}
              style={{ borderLeftColor: TEAM_COLORS[msg.sender] || '#666' }}
            >
              <div className={styles.msgHeader}>
                <span style={{ color: TEAM_COLORS[msg.sender] || '#666', fontWeight: 600 }}>
                  {msg.sender === 'user' ? '👤 ' : ''}{msg.sender_label}
                </span>
                {msg.type === 'result' && <span className={styles.resultBadge}>📋 详细结果</span>}
                {msg.type === 'discussion' && <span className={styles.discussBadge}>💬 讨论</span>}
                {msg.type === 'user_input' && <span className={styles.userBadge}>👤 用户</span>}
                <span className={styles.msgTime}>{formatTime(msg.timestamp)}</span>
              </div>
              <div className={msg.type === 'result' ? styles.msgContentResult : styles.msgContent}>
                {msg.content.split('\n').map((line, i) => {
                  if (line.startsWith('```')) return null;
                  if (line.startsWith('- ')) return <div key={i} className={styles.listItem}>{line.slice(2)}</div>;
                  if (line.startsWith('**') && line.endsWith('**')) return <div key={i} className={styles.boldLine}>{line.slice(2, -2)}</div>;
                  return <div key={i}>{line || ' '}</div>;
                })}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* 用户输入区域 */}
        <div className={styles.inputArea}>
          <div className={styles.inputRow}>
            <textarea
              className={styles.inputBox}
              placeholder={isWaiting ? 'Agent 正在等待您的反馈，请输入意见...' : '参与讨论：输入您的想法、建议或修正方向...'}
              value={userInput}
              onChange={e => setUserInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              disabled={sending}
            />
            <button
              className={styles.sendBtn}
              onClick={handleSend}
              disabled={!userInput.trim() || sending}
            >
              {sending ? '...' : '发送'}
            </button>
          </div>
          <div className={styles.inputHint}>
            Enter 发送 · Shift+Enter 换行 · 您的消息会实时出现在 Agent 讨论中
          </div>
        </div>
      </div>
    </div>
  );
}
