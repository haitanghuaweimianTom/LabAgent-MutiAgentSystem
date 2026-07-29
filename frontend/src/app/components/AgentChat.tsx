'use client';

import { useRef, useEffect, useState } from 'react';
import StageProgress from './StageProgress';
import { apiBase } from '@/lib/api';
import { TEAM_LABELS } from '@/lib/constants';
import { cn } from '@/lib/utils';

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
  workflowType?: string;
  paused: boolean;
  onPause: () => void;
  onResume: () => void;
  onCancel?: () => void;
  resuming: boolean;
  cancelling?: boolean;
  taskId?: string | null;
  onUserSend?: (content: string) => void;
}

// SSE event shape for chat_message
interface SSEChatMessage {
  type: 'chat_message';
  sender: string;
  sender_label: string;
  content: string;
  msg_type: string;
  timestamp: string;
}



function formatTime(iso: string) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString('zh-CN', { hour12: false }); } catch { return iso; }
}

type StageStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

function deriveStages(status: string, progress: number, currentStep: string, workflowType: string = 'standard') {
  const skipModeling = workflowType === 'deep_research' || workflowType === 'research_survey';

  const stages: { id: string; name: string; description: string; status: StageStatus; progress: number }[] = [
    { id: 'analysis', name: '问题分析', description: '数据预处理、子问题分解、文献搜集', status: 'pending', progress: 0 },
    { id: 'modeling', name: skipModeling ? '跳过建模' : '建模求解', description: skipModeling ? '调研/综述类工作流不经过建模求解' : '建模、代码生成、迭代验证', status: skipModeling ? 'skipped' : 'pending', progress: 0 },
    { id: 'writing', name: '论文写作', description: '章节生成、自评改进、LaTeX排版', status: 'pending', progress: 0 },
    { id: 'review', name: '同行评议', description: '4维评分、修订循环、Camera-Ready打包', status: 'pending', progress: 0 },
  ];

  if (status === 'idle' || status === 'pending') return stages;

  if (status === 'phase1' || status === 'running') {
    stages[0].status = 'running';
    stages[0].progress = Math.min(progress * 2, 100);

    if (!skipModeling) {
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
    } else {
      if (currentStep?.includes('论文') || currentStep?.includes('write')) {
        stages[0].status = 'completed';
        stages[1].status = 'skipped';
        stages[1].progress = 100;
        stages[2].status = 'running';
        stages[2].progress = Math.min((progress - 40) * 2.5, 100);
      }
      if (currentStep?.includes('评议') || currentStep?.includes('review') || currentStep?.includes('修订')) {
        stages[0].status = 'completed';
        stages[1].status = 'skipped';
        stages[1].progress = 100;
        stages[2].status = 'completed';
        stages[3].status = 'running';
        stages[3].progress = Math.min((progress - 80) * 5, 100);
      }
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
  messages, taskStatus, progress, currentStep, workflowType, paused, onPause, onResume, onCancel, resuming, cancelling,
  taskId, onUserSend,
}: AgentChatProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [userInput, setUserInput] = useState('');
  const [sending, setSending] = useState(false);
  const isNearBottomRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [sseMessages, setSseMessages] = useState<Message[]>([]);
  const stages = deriveStages(taskStatus, progress, currentStep || '', workflowType);

  // Merge prop messages with SSE messages (SSE messages appended after initial load)
  const allMessages = [...messages, ...sseMessages];

  // SSE connection for real-time chat messages
  useEffect(() => {
    if (!taskId) return;
    const es = new EventSource(apiBase() + '/tasks/' + taskId + '/stream');
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'chat_message') {
          const msg: Message = {
            id: `sse-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            sender: data.sender,
            sender_label: data.sender_label,
            content: data.content,
            type: data.msg_type || 'discussion',
            timestamp: data.timestamp,
          };
          setSseMessages(prev => [...prev, msg]);
        }
      } catch {}
    };
    es.onerror = () => { /* reconnect handled by EventSource */ };
    return () => es.close();
  }, [taskId]);

  const checkScrollPosition = () => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const threshold = 80;
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const nearBottom = distanceToBottom < threshold;
    isNearBottomRef.current = nearBottom;
    setShowScrollButton(!nearBottom);
  };

  const scrollToBottom = (behavior: ScrollBehavior = 'instant') => {
    messagesEndRef.current?.scrollIntoView({ behavior });
    isNearBottomRef.current = true;
    setShowScrollButton(false);
  };

  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    el.addEventListener('scroll', checkScrollPosition);
    return () => el.removeEventListener('scroll', checkScrollPosition);
  }, []);

  useEffect(() => {
    if (isNearBottomRef.current) {
      scrollToBottom('instant');
    }
  }, [allMessages]);

  const isRunning = taskStatus === 'running' || taskStatus === 'phase1' || taskStatus === 'phase2';
  const isWaiting = currentStep?.includes('waiting') || currentStep?.includes('等待');

  const handleSend = async () => {
    const content = userInput.trim();
    if (!content || !taskId) return;
    setSending(true);
    try {
      await fetch(`${apiBase()}/tasks/${taskId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      setUserInput('');
      onUserSend?.(content);
      scrollToBottom('instant');
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
    <div className="flex flex-col gap-4">
      <StageProgress stages={stages} currentStep={currentStep} />

      <div className="bg-card border border-border rounded-[14px] p-5 flex flex-col gap-3">
        <div className="flex justify-between items-center flex-wrap gap-2">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-lg text-foreground font-semibold">💬 Agent 团队实时讨论</span>
            <div className="flex gap-1.5 flex-wrap">
              {Object.entries(TEAM_LABELS).filter(([k]) => k !== 'system').map(([k, v]) => (
                <span key={k} className="px-2 py-0.5 rounded-lg text-sm text-muted-foreground font-medium whitespace-nowrap bg-muted border border-border">{v}</span>
              ))}
            </div>
          </div>
          <div className="flex gap-1.5">
            {isRunning && !paused && (
              <>
                <button className="py-1.5 px-3 bg-warning/15 border border-warning/30 rounded-md text-warning text-sm cursor-pointer transition-colors duration-150 hover:bg-warning/20" onClick={onPause}>⏸ 暂停</button>
                {onCancel && (
                  <button className="py-1.5 px-3 bg-error/10 border border-error/20 rounded-md text-error text-sm cursor-pointer transition-colors duration-150 hover:bg-error/15 disabled:opacity-50 disabled:cursor-not-allowed" onClick={onCancel} disabled={cancelling}>
                    {cancelling ? '取消中...' : '⏹ 取消'}
                  </button>
                )}
              </>
            )}
            {paused && (
              <button className="py-1.5 px-3 bg-success/10 border border-success/20 rounded-md text-success text-sm cursor-pointer transition-colors duration-150 hover:bg-success/15 disabled:opacity-50 disabled:cursor-not-allowed" onClick={onResume} disabled={resuming}>
                {resuming ? '继续中...' : '▶ 继续执行'}
              </button>
            )}
          </div>
        </div>

        <div className="h-[480px] overflow-y-auto p-3 bg-muted/50 rounded-md relative" ref={messagesContainerRef}>
          {allMessages.length === 0 && (
            <div className="text-center p-12 text-muted-foreground text-sm">提交问题后，各 Agent 将在此展开协作讨论</div>
          )}
          {allMessages.map(msg => (
            <div
              key={msg.id}
              className={cn(
                'p-3 mb-2 rounded-md border-l-2',
                msg.type === 'result'
                  ? 'bg-primary/10 border-primary'
                  : msg.type === 'user_input'
                    ? 'bg-primary/10 border-primary'
                    : msg.type === 'discussion'
                      ? 'bg-muted border-foreground/30'
                      : 'bg-card border-border'
              )}
            >
              <div className="flex justify-between mb-2 text-sm items-center">
                <span className="font-semibold text-foreground">
                  {msg.sender === 'user' ? '👤 ' : ''}{msg.sender_label}
                </span>
                {msg.type === 'result' && <span className="text-xs px-2 py-0.5 bg-primary/10 text-primary rounded-lg font-semibold">📋 详细结果</span>}
                {msg.type === 'discussion' && <span className="text-xs px-2 py-0.5 bg-muted text-foreground rounded-lg font-semibold">💬 讨论</span>}
                {msg.type === 'user_input' && <span className="text-xs px-2 py-0.5 bg-primary/10 text-primary rounded-lg font-semibold">👤 用户</span>}
                <span className="text-muted-foreground text-sm">{formatTime(msg.timestamp)}</span>
              </div>
              <div className={cn(
                'whitespace-pre-wrap text-foreground',
                msg.type === 'result'
                  ? 'text-sm leading-relaxed font-mono'
                  : 'text-sm leading-relaxed'
              )}>
                {msg.content.split('\n').map((line, i) => {
                  if (line.startsWith('```')) return null;
                  if (line.startsWith('- ')) return <div key={i} className="pl-2 text-muted-foreground">{line.slice(2)}</div>;
                  if (line.startsWith('**') && line.endsWith('**')) return <div key={i} className="font-bold text-foreground mt-1">{line.slice(2, -2)}</div>;
                  return <div key={i}>{line || ' '}</div>;
                })}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
          {showScrollButton && (
            <button
              className="sticky bottom-2 left-1/2 -translate-x-1/2 py-1.5 px-3.5 bg-primary/10 border-none rounded-2xl text-foreground text-sm font-semibold cursor-pointer shadow-md transition-colors duration-150 hover:bg-primary/15 z-10"
              onClick={() => scrollToBottom('instant')}
              title="回到最新消息"
            >
              ↓ 最新消息
            </button>
          )}
        </div>

        <div className="mt-2 pt-[0.5rem] border-t border-border">
          <div className="flex gap-2 items-end">
            <textarea
              className="flex-1 py-2.5 px-3 bg-background border border-input rounded-md text-foreground text-sm resize-none font-inherit leading-relaxed focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 placeholder:text-muted-foreground"
              placeholder={isWaiting ? 'Agent 正在等待您的反馈，请输入意见...' : '参与讨论：输入您的想法、建议或修正方向...'}
              value={userInput}
              onChange={e => setUserInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              disabled={sending}
            />
            <button
              className="py-2.5 px-4 bg-primary text-primary-foreground border-none rounded-md text-sm font-semibold cursor-pointer transition-opacity duration-150 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-90"
              onClick={handleSend}
              disabled={!userInput.trim() || sending}
            >
              {sending ? '...' : '发送'}
            </button>
          </div>
          <div className="mt-[0.3rem] text-xs text-muted-foreground text-center">
            Enter 发送 · Shift+Enter 换行 · 您的消息会实时出现在 Agent 讨论中
          </div>
        </div>
      </div>
    </div>
  );
}
