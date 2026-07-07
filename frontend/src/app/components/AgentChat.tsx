'use client';

import { useRef, useEffect, useState } from 'react';
import StageProgress from './StageProgress';
import { apiBase } from '@/lib/api';
import { TEAM_COLORS, TEAM_LABELS } from '@/lib/constants';
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

      <div className="bg-[#1E293B] border border-[#334155] rounded-[14px] p-[1.2rem] flex flex-col gap-[0.8rem]">
        <div className="flex justify-between items-center flex-wrap gap-2">
          <div className="flex items-center gap-[0.8rem] flex-wrap">
            <span className="text-[1.1rem] text-[#F8FAFC] font-semibold">💬 Agent 团队实时讨论</span>
            <div className="flex gap-[0.3rem] flex-wrap">
              {Object.entries(TEAM_LABELS).filter(([k]) => k !== 'system').map(([k, v]) => (
                <span key={k} className="px-[0.5rem] py-[0.2rem] rounded-[10px] text-[0.8125rem] text-[#F8FAFC] font-semibold whitespace-nowrap" style={{ background: TEAM_COLORS[k] }}>{v}</span>
              ))}
            </div>
          </div>
          <div className="flex gap-[0.4rem]">
            {isRunning && !paused && (
              <>
                <button className="py-[0.35rem] px-[0.8rem] bg-[rgba(243,156,18,0.3)] border border-[rgba(243,156,18,0.5)] rounded-[6px] text-[#f39c12] text-[0.875rem] cursor-pointer transition-all duration-200 hover:bg-[rgba(243,156,18,0.5)]" onClick={onPause}>⏸ 暂停</button>
                {onCancel && (
                  <button className="py-[0.35rem] px-[0.8rem] bg-[rgba(248,113,113,0.15)] border border-[rgba(248,113,113,0.15)] rounded-[6px] text-[#e74c3c] text-[0.875rem] cursor-pointer transition-all duration-200 hover:bg-[rgba(248,113,113,0.15)] disabled:opacity-50 disabled:cursor-not-allowed" onClick={onCancel} disabled={cancelling}>
                    {cancelling ? '取消中...' : '⏹ 取消'}
                  </button>
                )}
              </>
            )}
            {paused && (
              <button className="py-[0.35rem] px-[0.8rem] bg-[rgba(74,222,128,0.15)] border border-[rgba(74,222,128,0.15)] rounded-[6px] text-[#2ecc71] text-[0.875rem] cursor-pointer transition-all duration-200 hover:bg-[rgba(74,222,128,0.15)] disabled:opacity-50 disabled:cursor-not-allowed" onClick={onResume} disabled={resuming}>
                {resuming ? '继续中...' : '▶ 继续执行'}
              </button>
            )}
          </div>
        </div>

        <div className="h-[480px] overflow-y-auto p-[0.8rem] bg-[rgba(0,0,0,0.2)] rounded-[8px] relative" ref={messagesContainerRef}>
          {allMessages.length === 0 && (
            <div className="text-center p-[3rem] text-[#475569] text-[0.9375rem]">提交问题后，各 Agent 将在此展开协作讨论</div>
          )}
          {allMessages.map(msg => (
            <div
              key={msg.id}
              className={cn(
                'p-[0.7rem_0.9rem] mb-[0.5rem] rounded-[8px]',
                msg.type === 'result'
                  ? 'p-[0.8rem] mb-[0.6rem] rounded-[10px] bg-[rgba(45,212,191,0.15)] border border-[rgba(45,212,191,0.15)]'
                  : msg.type === 'user_input'
                    ? 'bg-[rgba(45,212,191,0.15)] border-l-[3px] border-[#3498db]'
                    : msg.type === 'discussion'
                      ? 'bg-[rgba(142,68,173,0.05)] border-l-[3px] border-[#8e44ad]'
                      : 'bg-[#1E293B] border-l-[3px] border-[#666]'
              )}
              style={{ borderLeftColor: TEAM_COLORS[msg.sender] || '#666' }}
            >
              <div className="flex justify-between mb-[0.5rem] text-[0.82rem] items-center">
                <span style={{ color: TEAM_COLORS[msg.sender] || '#666', fontWeight: 600 }}>
                  {msg.sender === 'user' ? '👤 ' : ''}{msg.sender_label}
                </span>
                {msg.type === 'result' && <span className="text-[0.8125rem] px-[0.5rem] py-[0.1rem] bg-[rgba(45,212,191,0.15)] text-[#3498db] rounded-[10px] font-semibold">📋 详细结果</span>}
                {msg.type === 'discussion' && <span className="text-[0.8125rem] px-[0.5rem] py-[0.1rem] bg-[rgba(142,68,173,0.2)] text-[#8e44ad] rounded-[10px] font-semibold">💬 讨论</span>}
                {msg.type === 'user_input' && <span className="text-[0.8125rem] px-[0.5rem] py-[0.1rem] bg-[rgba(45,212,191,0.15)] text-[#3498db] rounded-[10px] font-semibold">👤 用户</span>}
                <span className="text-[#475569] text-[0.875rem]">{formatTime(msg.timestamp)}</span>
              </div>
              <div className={cn(
                'whitespace-pre-wrap text-[#CBD5E1]',
                msg.type === 'result'
                  ? 'text-[0.9375rem] leading-[1.7] font-[\'Courier_New\',monospace]'
                  : 'text-[0.88rem] leading-[1.6]'
              )}>
                {msg.content.split('\n').map((line, i) => {
                  if (line.startsWith('```')) return null;
                  if (line.startsWith('- ')) return <div key={i} className="pl-[0.5rem] text-[#94A3B8]">{line.slice(2)}</div>;
                  if (line.startsWith('**') && line.endsWith('**')) return <div key={i} className="font-bold text-[#F8FAFC] mt-[0.3rem]">{line.slice(2, -2)}</div>;
                  return <div key={i}>{line || ' '}</div>;
                })}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
          {showScrollButton && (
            <button
              className="sticky bottom-[0.8rem] left-1/2 -translate-x-1/2 py-[0.4rem] px-[0.9rem] bg-[rgba(45,212,191,0.15)] border-none rounded-[20px] text-[#F8FAFC] text-[0.875rem] font-semibold cursor-pointer shadow-[0_2px_8px_rgba(0,0,0,0.3)] transition-all duration-200 hover:translate-y-[-1px] z-10"
              onClick={() => scrollToBottom('instant')}
              title="回到最新消息"
            >
              ↓ 最新消息
            </button>
          )}
        </div>

        <div className="mt-[0.5rem] pt-[0.5rem] border-t border-[#334155]">
          <div className="flex gap-2 items-end">
            <textarea
              className="flex-1 py-[0.6rem] px-[0.8rem] bg-[rgba(0,0,0,0.3)] border border-[#475569] rounded-[8px] text-[#e0e0e0] text-[0.9375rem] resize-none font-[inherit] leading-[1.5] focus:outline-none focus:border-[rgba(45,212,191,0.15)] focus:shadow-[0_0_0_2px_rgba(45,212,191,0.15)] placeholder:text-[#475569]"
              placeholder={isWaiting ? 'Agent 正在等待您的反馈，请输入意见...' : '参与讨论：输入您的想法、建议或修正方向...'}
              value={userInput}
              onChange={e => setUserInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              disabled={sending}
            />
            <button
              className="py-[0.6rem] px-4 bg-[#2DD4BF] text-[#F8FAFC] border-none rounded-[8px] text-[0.9375rem] font-semibold cursor-pointer transition-all duration-200 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={handleSend}
              disabled={!userInput.trim() || sending}
            >
              {sending ? '...' : '发送'}
            </button>
          </div>
          <div className="mt-[0.3rem] text-[0.72rem] text-[#475569] text-center">
            Enter 发送 · Shift+Enter 换行 · 您的消息会实时出现在 Agent 讨论中
          </div>
        </div>
      </div>
    </div>
  );
}
