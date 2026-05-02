'use client';

import { useRef, useEffect } from 'react';
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
  resuming: boolean;
}

const TEAM_COLORS: Record<string, string> = {
  coordinator: '#e74c3c',
  research_agent: '#3498db',
  data_agent: '#9b59b6',
  analyzer_agent: '#f39c12',
  modeler_agent: '#27ae60',
  solver_agent: '#e67e22',
  writer_agent: '#1abc9c',
  system: '#95a5a6',
  user: '#2ecc71',
};

const TEAM_LABELS: Record<string, string> = {
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

function formatTime(iso: string) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString('zh-CN', { hour12: false }); } catch { return iso; }
}

type StageStatus = 'pending' | 'running' | 'completed' | 'failed';

function deriveStages(status: string, progress: number, currentStep: string) {
  const stages: { id: string; name: string; description: string; status: StageStatus; progress: number }[] = [
    { id: 'analysis', name: '问题分析', description: '提取子任务、约束、数据需求', status: 'pending', progress: 0 },
    { id: 'modeling', name: '数学建模', description: '构建模型、公式、假设', status: 'pending', progress: 0 },
    { id: 'solving', name: '计算求解', description: '生成代码、执行、结果验证', status: 'pending', progress: 0 },
    { id: 'writing', name: '论文生成', description: '分段撰写、图表、LaTeX排版', status: 'pending', progress: 0 },
  ];

  if (status === 'idle' || status === 'pending') return stages;

  // Phase 1 includes analysis
  if (status === 'phase1' || status === 'running') {
    stages[0].status = 'running';
    stages[0].progress = Math.min(progress * 2, 100);
    if (currentStep?.includes('建模') || currentStep?.includes('model')) {
      stages[0].status = 'completed';
      stages[0].progress = 100;
      stages[1].status = 'running';
      stages[1].progress = Math.min((progress - 20) * 1.5, 100);
    }
    if (currentStep?.includes('求解') || currentStep?.includes('solve')) {
      stages[0].status = 'completed';
      stages[1].status = 'completed';
      stages[2].status = 'running';
      stages[2].progress = Math.min((progress - 40) * 2, 100);
    }
    if (currentStep?.includes('论文') || currentStep?.includes('write')) {
      stages[0].status = 'completed';
      stages[1].status = 'completed';
      stages[2].status = 'completed';
      stages[3].status = 'running';
      stages[3].progress = Math.min((progress - 60) * 2.5, 100);
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

export default function AgentChat({ messages, taskStatus, progress, currentStep, paused, onPause, onResume, resuming }: AgentChatProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const stages = deriveStages(taskStatus, progress, currentStep || '');

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const isRunning = taskStatus === 'running' || taskStatus === 'phase1' || taskStatus === 'phase2';

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
              <button className={styles.pauseBtn} onClick={onPause}>⏸ 暂停</button>
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
              className={msg.type === 'result' ? styles.msgResult : styles.msg}
              style={{ borderLeftColor: TEAM_COLORS[msg.sender] || '#666' }}
            >
              <div className={styles.msgHeader}>
                <span style={{ color: TEAM_COLORS[msg.sender] || '#666', fontWeight: 600 }}>
                  {msg.sender_label}
                </span>
                {msg.type === 'result' && <span className={styles.resultBadge}>📋 详细结果</span>}
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
      </div>
    </div>
  );
}
