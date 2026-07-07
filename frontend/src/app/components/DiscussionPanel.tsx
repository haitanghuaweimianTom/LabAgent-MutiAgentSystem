'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { apiBase } from '@/lib/api';

interface DiscussionMessage {
  id: string;
  sender: string;
  sender_label: string;
  content: string;
  type: 'agent' | 'user' | 'system';
  timestamp: string;
}

interface Vote {
  id: string;
  voter: string;
  voter_label: string;
  choice: 'approve' | 'reject' | 'abstain';
  reason?: string;
  timestamp: string;
}

interface DiscussionRound {
  round_number: number;
  topic: string;
  messages: DiscussionMessage[];
  votes: Vote[];
  status: 'active' | 'voting' | 'concluded';
  conclusion?: string;
}

interface DiscussionState {
  task_id: string;
  topic: string;
  status: 'pending' | 'active' | 'voting' | 'decided' | 'cancelled';
  current_round: number;
  rounds: DiscussionRound[];
  human_decision?: 'approve' | 'reject' | 'modify';
  human_decision_note?: string;
  created_at: string;
  updated_at: string;
}

interface DiscussionPanelProps {
  taskId: string;
  onClose?: () => void;
}

function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function getAgentColor(name: string): string {
  const colors = [
    '#e74c3c', '#3498db', '#9b59b6', '#f39c12', '#27ae60',
    '#16a085', '#d4ac0d', '#e67e22', '#1abc9c', '#8e44ad',
    '#2c3e50', '#e84393', '#00b894', '#fd79a8', '#6c5ce7',
  ];
  return colors[hashString(name) % colors.length];
}

function formatTime(iso: string): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false });
  } catch {
    return iso;
  }
}

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  pending: { label: '等待中', color: '#94A3B8', bg: 'rgba(148,163,184,0.1)' },
  active: { label: '讨论进行中', color: '#3B82F6', bg: 'rgba(59,130,246,0.1)' },
  voting: { label: '投票中', color: '#F59E0B', bg: 'rgba(245,158,11,0.1)' },
  decided: { label: '已决定', color: '#10B981', bg: 'rgba(16,185,129,0.1)' },
  cancelled: { label: '已取消', color: '#EF4444', bg: 'rgba(239,68,68,0.1)' },
};

const ROUND_STATUS: Record<string, { label: string; color: string }> = {
  active: { label: '讨论中', color: '#3B82F6' },
  voting: { label: '投票中', color: '#F59E0B' },
  concluded: { label: '已结束', color: '#10B981' },
};

export default function DiscussionPanel({ taskId, onClose }: DiscussionPanelProps) {
  const [state, setState] = useState<DiscussionState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [userInput, setUserInput] = useState('');
  const [sending, setSending] = useState(false);
  const [voting, setVoting] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [humanNote, setHumanNote] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);

  const fetchDiscussion = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase()}/discussions/${taskId}`);
      if (!res.ok) {
        if (res.status === 404) {
          setError('讨论不存在');
          return;
        }
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setState(data);
      setError(null);
    } catch (e: any) {
      setError(e.message || '加载讨论失败');
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    fetchDiscussion();
  }, [fetchDiscussion]);

  // SSE connection for real-time chat messages
  useEffect(() => {
    if (!taskId) return;
    const es = new EventSource(apiBase() + '/tasks/' + taskId + '/stream');
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'chat_message') {
          const newMsg: DiscussionMessage = {
            id: `sse-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            sender: data.sender,
            sender_label: data.sender_label,
            content: data.content,
            type: (data.msg_type as DiscussionMessage['type']) || 'agent',
            timestamp: data.timestamp,
          };
          setState(prev => {
            if (!prev) return prev;
            const rounds = [...prev.rounds];
            if (rounds.length === 0) {
              rounds.push({ round_number: 1, topic: prev.topic, messages: [newMsg], votes: [], status: 'active' });
            } else {
              const last = { ...rounds[rounds.length - 1] };
              last.messages = [...last.messages, newMsg];
              rounds[rounds.length - 1] = last;
            }
            return { ...prev, rounds, updated_at: new Date().toISOString() };
          });
        }
      } catch {}
    };
    es.onerror = () => { /* reconnect handled by EventSource */ };
    return () => es.close();
  }, [taskId]);

  useEffect(() => {
    if (isNearBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'instant' });
    }
  }, [state?.rounds]);

  const checkScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    isNearBottomRef.current = dist < 80;
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'instant' });
    isNearBottomRef.current = true;
  };

  const handleSend = async () => {
    const content = userInput.trim();
    if (!content || sending) return;
    setSending(true);
    try {
      const res = await fetch(`${apiBase()}/discussions/${taskId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setUserInput('');
      scrollToBottom();
      await fetchDiscussion();
    } catch (e: any) {
      console.error('发送消息失败:', e);
    } finally {
      setSending(false);
    }
  };

  const handleVote = async (choice: 'approve' | 'reject' | 'abstain') => {
    if (voting) return;
    setVoting(true);
    try {
      const res = await fetch(`${apiBase()}/discussions/${taskId}/vote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ choice }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchDiscussion();
    } catch (e: any) {
      console.error('投票失败:', e);
    } finally {
      setVoting(false);
    }
  };

  const handleDecide = async (decision: 'approve' | 'reject' | 'modify') => {
    if (deciding) return;
    setDeciding(true);
    try {
      const res = await fetch(`${apiBase()}/discussions/${taskId}/human-decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, note: humanNote.trim() || undefined }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setHumanNote('');
      await fetchDiscussion();
    } catch (e: any) {
      console.error('决策失败:', e);
    } finally {
      setDeciding(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (loading) {
    return (
      <div style={styles.overlay}>
        <div style={styles.panel}>
          <div style={styles.loading}>加载讨论中...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.overlay}>
        <div style={styles.panel}>
          <div style={styles.errorState}>{error}</div>
          <button style={styles.closeBtn} onClick={onClose}>关闭</button>
        </div>
      </div>
    );
  }

  const st = state!;
  const statusCfg = STATUS_CONFIG[st.status] || STATUS_CONFIG.pending;

  return (
    <div style={styles.overlay}>
      <div style={styles.panel}>
        {/* Decision banner */}
        <div style={{ ...styles.banner, background: statusCfg.bg, borderBottom: `2px solid ${statusCfg.color}` }}>
          <div style={styles.bannerLeft}>
            <span style={{ ...styles.bannerStatus, color: statusCfg.color }}>{statusCfg.label}</span>
            <span style={styles.bannerTopic}>{st.topic}</span>
            <span style={styles.bannerRound}>第 {st.current_round} 轮</span>
          </div>
          {onClose && (
            <button style={styles.closeBtn} onClick={onClose} title="关闭">✕</button>
          )}
        </div>

        {/* Human decision banner */}
        {st.human_decision && (
          <div style={{
            ...styles.humanBanner,
            background: st.human_decision === 'approve' ? 'rgba(16,185,129,0.1)' : st.human_decision === 'reject' ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)',
            borderColor: st.human_decision === 'approve' ? '#10B981' : st.human_decision === 'reject' ? '#EF4444' : '#F59E0B',
          }}>
            <span style={{ fontWeight: 600 }}>
              最终决定: {st.human_decision === 'approve' ? '✓ 批准' : st.human_decision === 'reject' ? '✗ 驳回' : '✎ 需修改'}
            </span>
            {st.human_decision_note && <span style={{ marginLeft: 8, color: '#94A3B8' }}>{st.human_decision_note}</span>}
          </div>
        )}

        {/* Messages area */}
        <div style={styles.messagesContainer} ref={containerRef} onScroll={checkScroll}>
          {st.rounds.length === 0 && (
            <div style={styles.emptyState}>暂无讨论内容</div>
          )}

          {st.rounds.map(round => (
            <div key={round.round_number} style={styles.roundSection}>
              <div style={styles.roundHeader}>
                <span style={styles.roundTitle}>第 {round.round_number} 轮</span>
                {round.topic && <span style={styles.roundTopic}>{round.topic}</span>}
                <span style={{ ...styles.roundBadge, color: ROUND_STATUS[round.status]?.color || '#94A3B8' }}>
                  {ROUND_STATUS[round.status]?.label || round.status}
                </span>
              </div>

              {round.messages.map(msg => {
                const isUser = msg.type === 'user';
                const isSystem = msg.type === 'system';
                const agentColor = isUser ? '#10B981' : isSystem ? '#6B7280' : getAgentColor(msg.sender);

                return (
                  <div key={msg.id} style={{
                    ...styles.message,
                    ...(isUser ? styles.messageUser : {}),
                    ...(isSystem ? styles.messageSystem : {}),
                    borderLeftColor: agentColor,
                  }}>
                    <div style={styles.messageHeader}>
                      <div style={{ ...styles.avatar, background: agentColor }}>
                        {isUser ? 'U' : isSystem ? 'S' : msg.sender_label?.[0] || '?'}
                      </div>
                      <span style={{ ...styles.senderName, color: agentColor }}>
                        {msg.sender_label || msg.sender}
                      </span>
                      {isUser && <span style={styles.userBadge}>用户</span>}
                      <span style={styles.msgTime}>{formatTime(msg.timestamp)}</span>
                    </div>
                    <div style={styles.messageContent}>
                      {msg.content.split('\n').map((line, i) => (
                        <div key={i}>{line || '\u00A0'}</div>
                      ))}
                    </div>
                  </div>
                );
              })}

              {/* Votes display for this round */}
              {round.votes.length > 0 && (
                <div style={styles.votesSection}>
                  <div style={styles.votesTitle}>投票结果</div>
                  <div style={styles.votesList}>
                    {round.votes.map(v => (
                      <div key={v.id} style={styles.voteItem}>
                        <span style={{
                          ...styles.voteChoice,
                          color: v.choice === 'approve' ? '#10B981' : v.choice === 'reject' ? '#EF4444' : '#6B7280',
                        }}>
                          {v.choice === 'approve' ? '✓ 赞成' : v.choice === 'reject' ? '✗ 反对' : '— 弃权'}
                        </span>
                        <span style={styles.voteVoter}>{v.voter_label || v.voter}</span>
                        {v.reason && <span style={styles.voteReason}>{v.reason}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {round.conclusion && (
                <div style={styles.roundConclusion}>{round.conclusion}</div>
              )}
            </div>
          ))}

          <div ref={messagesEndRef} />
        </div>

        {/* Action area */}
        {st.status === 'active' && (
          <div style={styles.actionBar}>
            <div style={styles.inputRow}>
              <textarea
                style={styles.textarea}
                placeholder="输入您的意见参与讨论..."
                value={userInput}
                onChange={e => setUserInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={2}
                disabled={sending}
              />
              <button
                style={{ ...styles.sendBtn, opacity: (!userInput.trim() || sending) ? 0.5 : 1 }}
                onClick={handleSend}
                disabled={!userInput.trim() || sending}
              >
                {sending ? '...' : '发送'}
              </button>
            </div>
            <div style={styles.hint}>Enter 发送 · Shift+Enter 换行</div>
          </div>
        )}

        {st.status === 'voting' && (
          <div style={styles.voteBar}>
            <div style={styles.voteBarTitle}>请投票</div>
            <div style={styles.voteButtons}>
              <button
                style={{ ...styles.voteBtn, ...styles.voteBtnApprove }}
                onClick={() => handleVote('approve')}
                disabled={voting}
              >
                {voting ? '...' : '✓ 赞成'}
              </button>
              <button
                style={{ ...styles.voteBtn, ...styles.voteBtnReject }}
                onClick={() => handleVote('reject')}
                disabled={voting}
              >
                {voting ? '...' : '✗ 反对'}
              </button>
              <button
                style={{ ...styles.voteBtn, ...styles.voteBtnAbstain }}
                onClick={() => handleVote('abstain')}
                disabled={voting}
              >
                {voting ? '...' : '— 弃权'}
              </button>
            </div>
          </div>
        )}

        {st.status === 'active' && (
          <div style={styles.decideBar}>
            <div style={styles.decideRow}>
              <input
                style={styles.decideInput}
                placeholder="备注（可选）"
                value={humanNote}
                onChange={e => setHumanNote(e.target.value)}
              />
              <button style={{ ...styles.decideBtn, ...styles.decideBtnApprove }} onClick={() => handleDecide('approve')} disabled={deciding}>
                批准
              </button>
              <button style={{ ...styles.decideBtn, ...styles.decideBtnModify }} onClick={() => handleDecide('modify')} disabled={deciding}>
                需修改
              </button>
              <button style={{ ...styles.decideBtn, ...styles.decideBtnReject }} onClick={() => handleDecide('reject')} disabled={deciding}>
                驳回
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.6)',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 9999,
  },
  panel: {
    width: '90vw',
    maxWidth: 900,
    height: '85vh',
    background: '#1E293B',
    borderRadius: 12,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    color: '#E2E8F0',
    fontFamily: 'system-ui, -apple-system, sans-serif',
    boxShadow: '0 25px 50px rgba(0,0,0,0.5)',
  },
  loading: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100%',
    color: '#94A3B8',
    fontSize: 16,
  },
  errorState: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100%',
    color: '#EF4444',
    fontSize: 16,
  },
  banner: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 20px',
    flexShrink: 0,
  },
  bannerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
  },
  bannerStatus: {
    fontWeight: 700,
    fontSize: 14,
  },
  bannerTopic: {
    fontSize: 15,
    fontWeight: 500,
  },
  bannerRound: {
    fontSize: 12,
    color: '#94A3B8',
    background: 'rgba(148,163,184,0.1)',
    padding: '2px 8px',
    borderRadius: 4,
  },
  humanBanner: {
    padding: '10px 20px',
    fontSize: 14,
    borderBottom: '1px solid rgba(255,255,255,0.05)',
    display: 'flex',
    alignItems: 'center',
    flexShrink: 0,
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: '#94A3B8',
    fontSize: 18,
    cursor: 'pointer',
    padding: '4px 8px',
  },
  messagesContainer: {
    flex: 1,
    overflowY: 'auto',
    padding: 16,
  },
  emptyState: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100%',
    color: '#64748B',
    fontSize: 15,
  },
  roundSection: {
    marginBottom: 24,
  },
  roundHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
    paddingBottom: 8,
    borderBottom: '1px solid rgba(255,255,255,0.06)',
  },
  roundTitle: {
    fontWeight: 700,
    fontSize: 14,
    color: '#3B82F6',
  },
  roundTopic: {
    fontSize: 13,
    color: '#94A3B8',
  },
  roundBadge: {
    fontSize: 11,
    fontWeight: 600,
    marginLeft: 'auto',
  },
  message: {
    borderLeft: '3px solid #6B7280',
    background: 'rgba(255,255,255,0.03)',
    borderRadius: '0 8px 8px 0',
    padding: '10px 14px',
    marginBottom: 8,
  },
  messageUser: {
    background: 'rgba(16,185,129,0.08)',
    borderLeftColor: '#10B981',
  },
  messageSystem: {
    background: 'rgba(107,114,128,0.08)',
    borderLeftColor: '#6B7280',
    fontStyle: 'italic',
  },
  messageHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginBottom: 4,
  },
  avatar: {
    width: 24,
    height: 24,
    borderRadius: 12,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 11,
    fontWeight: 700,
    color: '#fff',
    flexShrink: 0,
  },
  senderName: {
    fontWeight: 600,
    fontSize: 13,
  },
  userBadge: {
    fontSize: 10,
    fontWeight: 600,
    background: 'rgba(16,185,129,0.15)',
    color: '#10B981',
    padding: '1px 6px',
    borderRadius: 4,
  },
  msgTime: {
    fontSize: 11,
    color: '#64748B',
    marginLeft: 'auto',
  },
  messageContent: {
    fontSize: 13,
    lineHeight: 1.6,
    color: '#CBD5E1',
    paddingLeft: 32,
  },
  votesSection: {
    marginTop: 8,
    marginBottom: 8,
    padding: '8px 12px',
    background: 'rgba(255,255,255,0.03)',
    borderRadius: 8,
  },
  votesTitle: {
    fontSize: 12,
    fontWeight: 600,
    color: '#94A3B8',
    marginBottom: 6,
  },
  votesList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  voteItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    fontSize: 12,
  },
  voteChoice: {
    fontWeight: 600,
    minWidth: 60,
  },
  voteVoter: {
    color: '#CBD5E1',
  },
  voteReason: {
    color: '#64748B',
    fontStyle: 'italic',
  },
  roundConclusion: {
    marginTop: 8,
    padding: '8px 12px',
    background: 'rgba(16,185,129,0.06)',
    borderRadius: 8,
    fontSize: 13,
    color: '#94A3B8',
    borderLeft: '3px solid #10B981',
  },
  actionBar: {
    borderTop: '1px solid rgba(255,255,255,0.06)',
    padding: '12px 16px',
    flexShrink: 0,
  },
  inputRow: {
    display: 'flex',
    gap: 8,
    alignItems: 'flex-end',
  },
  textarea: {
    flex: 1,
    background: '#0F172A',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: 8,
    padding: '8px 12px',
    color: '#E2E8F0',
    fontSize: 13,
    resize: 'none',
    outline: 'none',
    fontFamily: 'inherit',
  },
  sendBtn: {
    background: '#3B82F6',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    padding: '8px 16px',
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
  },
  hint: {
    fontSize: 11,
    color: '#64748B',
    marginTop: 4,
  },
  voteBar: {
    borderTop: '1px solid rgba(255,255,255,0.06)',
    padding: '12px 16px',
    flexShrink: 0,
  },
  voteBarTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: '#F59E0B',
    marginBottom: 8,
  },
  voteButtons: {
    display: 'flex',
    gap: 8,
  },
  voteBtn: {
    flex: 1,
    padding: '10px 0',
    border: 'none',
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    color: '#fff',
  },
  voteBtnApprove: { background: '#10B981' },
  voteBtnReject: { background: '#EF4444' },
  voteBtnAbstain: { background: '#6B7280' },
  decideBar: {
    borderTop: '1px solid rgba(255,255,255,0.06)',
    padding: '10px 16px',
    flexShrink: 0,
  },
  decideRow: {
    display: 'flex',
    gap: 8,
    alignItems: 'center',
  },
  decideInput: {
    flex: 1,
    background: '#0F172A',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: 8,
    padding: '8px 12px',
    color: '#E2E8F0',
    fontSize: 13,
    outline: 'none',
    fontFamily: 'inherit',
  },
  decideBtn: {
    padding: '8px 14px',
    border: 'none',
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    color: '#fff',
  },
  decideBtnApprove: { background: '#10B981' },
  decideBtnModify: { background: '#F59E0B' },
  decideBtnReject: { background: '#EF4444' },
};
