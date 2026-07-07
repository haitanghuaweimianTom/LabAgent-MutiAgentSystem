'use client';

import { useState, useEffect } from 'react';
import PaperPreview from './PaperPreview';
import AlgorithmRecommend from './AlgorithmRecommend';
import PaperList from './PaperList';
import { useTaskState } from '../hooks/useTaskState';
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

interface TaskDetailProps {
  taskId: string;
  onDelete: () => void;
  onRerun?: (newTaskId: string) => void;
}

function formatTime(iso: string) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString('zh-CN', { hour12: false }); } catch { return iso; }
}

export default function TaskDetail({ taskId, onDelete, onRerun }: TaskDetailProps) {
  const [activeTab, setActiveTab] = useState<'messages' | 'result' | 'peer_review' | 'info'>('messages');
  const taskState = useTaskState({ taskId });
  const [messages, setMessages] = useState<Message[]>([]);
  const [result, setResult] = useState<any>(null);
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [rerunning, setRerunning] = useState(false);
  const [feedback, setFeedback] = useState({ overall: 5, category: 'method_selection', comment: '' });
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [msgRes, resultRes, metaRes] = await Promise.all([
          fetch(apiBase() + '/tasks/' + taskId + '/messages'),
          fetch(apiBase() + '/tasks/' + taskId + '/result'),
          fetch(apiBase() + '/tasks/' + taskId + '/status'),
        ]);
        if (msgRes.ok) {
          const msgs = await msgRes.json();
          setMessages(msgs.map((m: any) => ({
            id: m.id,
            sender: m.sender,
            sender_label: m.sender_label || TEAM_LABELS[m.sender] || m.sender,
            content: m.content,
            type: m.type || 'text',
            timestamp: m.timestamp,
          })));
        }
        if (resultRes.ok) {
          setResult(await resultRes.json());
        }
        if (metaRes.ok) {
          setMeta(await metaRes.json());
        }
      } catch {}
      setLoading(false);
    };
    load();
  }, [taskId]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await fetch(apiBase() + '/tasks/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId }),
      });
      const data = await res.json();
      if (data.success) {
        alert(`已导出到桌面：\n${data.output_dir}\n\n文件：${data.files.join('\n')}`);
      } else {
        alert('导出失败');
      }
    } catch { alert('导出失败'); } finally { setExporting(false); }
  };

  const handleCancel = async () => {
    if (!confirm('确定取消该任务？')) return;
    setCancelling(true);
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: '用户手动取消' }),
      });
      if (res.ok) {
        setCancelled(true);
        if (meta) setMeta({ ...meta, status: 'cancelled' });
      } else {
        alert('取消失败');
      }
    } catch { alert('取消失败'); } finally { setCancelling(false); }
  };

  const canRerun = meta?.status && ['completed', 'failed', 'cancelled', 'interrupted', 'cannot_solve'].includes(meta.status);

  const handleRerun = async () => {
    if (!confirm('将使用当前系统配置重新执行此任务，是否继续？')) return;
    setRerunning(true);
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/rerun', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template: meta?.template,
          workflow_type: meta?.workflow_type,
          mode: meta?.mode,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        alert(`✅ 新任务已创建: ${data.task_id}\n使用配置: ${data.template} / ${data.workflow_type}`);
        if (onRerun) onRerun(data.task_id);
      } else {
        const err = await res.json().catch(() => ({}));
        alert(`重新执行失败: ${err.detail || res.status}`);
      }
    } catch { alert('重新执行失败'); } finally { setRerunning(false); }
  };

  const handleSubmitFeedback = async () => {
    setSubmittingFeedback(true);
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback }),
      });
      if (res.ok) {
        setFeedbackSent(true);
      } else {
        alert('反馈提交失败');
      }
    } catch { alert('反馈提交失败'); } finally { setSubmittingFeedback(false); }
  };

  const renderMsg = (msg: Message) => (
    <div
      key={msg.id}
      className={cn(
        'p-[0.7rem_0.9rem] mb-[0.5rem] rounded-[8px] border-l-[3px] border-[#666] bg-[#1E293B]',
        msg.type === 'result' && 'p-[0.8rem] mb-[0.6rem] rounded-[10px] bg-[rgba(45,212,191,0.15)] border border-[rgba(45,212,191,0.15)] border-l-[4px] border-l-[#3498db]'
      )}
      style={{ borderLeftColor: TEAM_COLORS[msg.sender] || '#666' }}
    >
      <div className="flex justify-between mb-[0.5rem] text-[0.82rem] items-center">
        <span style={{ color: TEAM_COLORS[msg.sender] || '#666', fontWeight: 600 }}>{msg.sender_label}</span>
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
  );

  const algorithms = result?.output?.algorithms || result?.output?.modeler_agent?.algorithms || [];
  const latexCode = result?.output?.latex_code || result?.latex_code || '';
  const abstract = result?.output?.abstract || result?.abstract || '';
  const keywords = result?.output?.keywords || result?.keywords || [];
  const markdown = result?.output?.markdown || result?.output?.paper || '';

  return (
    <div className="flex flex-col gap-[0.8rem] h-full">
      <div className="flex justify-between items-center flex-wrap gap-2">
        <span className="text-[1rem] text-[#F8FAFC] font-semibold">📄 任务详情: {taskId}</span>
        <div className="flex gap-[0.4rem]">
          {meta?.status === 'running' && !cancelled && (
            <button className="py-[0.35rem] px-[0.9rem] bg-[rgba(248,113,113,0.15)] border border-[rgba(248,113,113,0.15)] rounded-[6px] text-[#e74c3c] text-[0.78rem] cursor-pointer transition-all duration-200 hover:bg-[rgba(248,113,113,0.15)] disabled:opacity-50 disabled:cursor-not-allowed" onClick={handleCancel} disabled={cancelling}>
              {cancelling ? '取消中...' : '⏹ 取消任务'}
            </button>
          )}
          <button className="py-[0.35rem] px-[0.9rem] bg-[rgba(74,222,128,0.15)] border border-[rgba(74,222,128,0.15)] rounded-[6px] text-[#2ecc71] text-[0.78rem] cursor-pointer transition-all duration-200 hover:bg-[rgba(74,222,128,0.15)] disabled:opacity-50 disabled:cursor-not-allowed" onClick={handleExport} disabled={exporting}>
            {exporting ? '导出中...' : '💾 导出到桌面'}
          </button>
          {canRerun && (
            <button className="py-[0.35rem] px-[0.9rem] bg-[rgba(74,222,128,0.15)] border border-[rgba(74,222,128,0.15)] rounded-[6px] text-[#2ecc71] text-[0.78rem] cursor-pointer transition-all duration-200 hover:bg-[rgba(74,222,128,0.15)] disabled:opacity-50 disabled:cursor-not-allowed" onClick={handleRerun} disabled={rerunning}>
              {rerunning ? '创建中...' : '🔄 重新执行'}
            </button>
          )}
          <button className="py-[0.35rem] px-[0.9rem] bg-[rgba(248,113,113,0.15)] border border-[rgba(248,113,113,0.15)] rounded-[6px] text-[#e74c3c] text-[0.78rem] cursor-pointer transition-all duration-200 hover:bg-[rgba(248,113,113,0.15)]" onClick={onDelete}>🗑️ 删除</button>
        </div>
      </div>

      {taskState.state && taskState.state.name !== 'completed' && taskState.state.name !== 'failed' && (
        <div className="relative w-full h-[28px] bg-[rgba(0,0,0,0.3)] rounded-[6px] overflow-hidden border border-[#334155]">
          <div
            className="h-full bg-gradient-to-r from-[rgba(45,212,191,0.15)] to-[rgba(74,222,128,0.15)] transition-[width] duration-500 rounded-[6px]"
            style={{ width: `${taskState.state.progressPercentage}%` }}
          />
          <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[0.875rem] text-[#F8FAFC] font-medium shadow-[0_1px_2px_rgba(0,0,0,0.5)] whitespace-nowrap">
            {taskState.state.progressPercentage}% · {taskState.state.currentStep || '运行中...'}
          </span>
        </div>
      )}

      <div className="flex gap-[0.3rem] border-b border-[#334155] pb-2">
        {(['messages', 'result', 'peer_review', 'info'] as const).map(t => (
          <button
            key={t}
            className={cn(
              'py-[0.4rem] px-[0.8rem] rounded-[6px] text-[0.82rem] cursor-pointer transition-all duration-200 border border-[#334155] bg-[#1E293B] text-[#94A3B8] hover:bg-[#334155] hover:text-[#CBD5E1]',
              activeTab === t && 'bg-[rgba(45,212,191,0.15)] border-[rgba(45,212,191,0.15)] text-[#3498db]'
            )}
            onClick={() => setActiveTab(t)}
          >
            {t === 'messages' && '💬 讨论记录'}
            {t === 'result' && '📊 结果'}
            {t === 'peer_review' && '🔍 同行评议'}
            {t === 'info' && 'ℹ️ 详情'}
          </button>
        ))}
      </div>

      {loading && <div className="text-center p-[2rem] text-[#475569] text-[0.9375rem]">加载中...</div>}

      {!loading && activeTab === 'messages' && (
        <div className="flex-1 overflow-y-auto max-h-[520px] p-[0.5rem] bg-[rgba(0,0,0,0.2)] rounded-[8px]">
          {messages.length === 0 ? <div className="text-center p-[2rem] text-[#475569] text-[0.9375rem]">暂无讨论记录</div> : messages.map(renderMsg)}
        </div>
      )}

      {!loading && activeTab === 'result' && (
        <div className="flex-1 overflow-y-auto max-h-[520px] flex flex-col gap-[0.8rem]">
          {(() => {
            const researchOutput = result?.output?.research_agent;
            const papers = researchOutput?.papers || result?.output?.papers || [];
            const source = researchOutput?.paper_source || 'arXiv';
            if (papers.length > 0) {
              return <PaperList papers={papers} source={source} />;
            }
            return null;
          })()}
          {algorithms.length > 0 && (
            <AlgorithmRecommend algorithms={algorithms} />
          )}
          <PaperPreview
            markdown={markdown}
            latexCode={latexCode}
            abstract={abstract}
            keywords={keywords}
          />
          {result?.output?.analyses && result.output.analyses.length > 0 && (
            <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4">
              <div className="text-[0.9375rem] text-[#3498db] font-bold mb-2">📊 数据分析</div>
              {result.output.analyses.map((a: any, i: number) => (
                <div key={i} className="bg-[rgba(0,0,0,0.3)] rounded-[8px] p-[0.7rem] mb-[0.4rem] text-[0.84rem] text-[#94A3B8] border border-[#334155]">
                  <strong className="text-[#F8FAFC]">{a.file_name}</strong>
                  <span> {a.shape?.[0]}行 × {a.shape?.[1]}列</span>
                  <div>{a.data_quality?.missing_rate === 0 ? '✓ 无缺失值' : `⚠ 缺失率 ${a.data_quality?.missing_rate}`}</div>
                  {(a.insights || []).map((ins: string, j: number) => (
                    <div key={j} className="pl-[0.5rem] text-[#94A3B8]">• {ins}</div>
                  ))}
                </div>
              ))}
            </div>
          )}

          {result?.output?.requirement_plan && (
            <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4">
              <div className="text-[0.9375rem] text-[#3498db] font-bold mb-2">📋 需求分解计划</div>
              <div style={{ marginBottom: 8, color: '#60a5fa', fontWeight: 600 }}>
                {result.output.requirement_plan.research_goal}
              </div>
              {result.output.requirement_plan.background && (
                <div style={{ marginBottom: 8, color: '#ccc', fontSize: '0.9rem' }}>
                  {result.output.requirement_plan.background}
                </div>
              )}
              {result.output.requirement_plan.key_questions?.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <strong style={{ color: '#E2E8F0' }}>核心问题：</strong>
                  {result.output.requirement_plan.key_questions.map((q: string, i: number) => (
                    <div key={i} style={{ color: '#aaa', fontSize: '0.85rem', marginLeft: 12 }}>• {q}</div>
                  ))}
                </div>
              )}
              {result.output.requirement_plan.subtasks?.length > 0 && (
                <div>
                  <strong style={{ color: '#E2E8F0' }}>子任务：</strong>
                  {result.output.requirement_plan.subtasks.map((t: any, i: number) => (
                    <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center', marginLeft: 12, marginTop: 4 }}>
                      <span style={{
                        padding: '2px 6px', borderRadius: 4, fontSize: '0.75rem',
                        background: t.priority === 'high' ? 'rgba(239,68,68,0.2)' : t.priority === 'medium' ? 'rgba(234,179,8,0.2)' : 'rgba(34,197,94,0.2)',
                        color: t.priority === 'high' ? '#f87171' : t.priority === 'medium' ? '#facc15' : '#4ade80',
                      }}>
                        {t.priority}
                      </span>
                      <span style={{ color: '#ccc', fontSize: '0.85rem' }}>{t.description}</span>
                      <span style={{ color: '#888', fontSize: '0.75rem' }}>→ {t.suggested_agent}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {result?.output?.innovation_analysis && (
            <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4">
              <div className="text-[0.9375rem] text-[#3498db] font-bold mb-2">💡 创新发现分析</div>
              {result.output.innovation_analysis.research_gaps?.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <strong style={{ color: '#E2E8F0' }}>研究空白：</strong>
                  {result.output.innovation_analysis.research_gaps.map((g: any, i: number) => (
                    <div key={i} style={{ marginLeft: 12, marginTop: 6, padding: '6px 10px', background: 'rgba(59,130,246,0.1)', borderRadius: 6, borderLeft: '3px solid #3B82F6' }}>
                      <div style={{ color: '#93c5fd', fontSize: '0.85rem', fontWeight: 600 }}>
                        Gap #{g.gap_id} <span style={{ color: g.importance === 'high' ? '#f87171' : '#facc15' }}>({g.importance})</span>
                      </div>
                      <div style={{ color: '#ccc', fontSize: '0.85rem' }}>{g.description}</div>
                      {g.opportunity && <div style={{ color: '#888', fontSize: '0.8rem', marginTop: 2 }}>机会：{g.opportunity}</div>}
                    </div>
                  ))}
                </div>
              )}
              {result.output.innovation_analysis.innovation_ideas?.length > 0 && (
                <div>
                  <strong style={{ color: '#E2E8F0' }}>创新方案：</strong>
                  {result.output.innovation_analysis.innovation_ideas.map((idea: any, i: number) => (
                    <div key={i} style={{ marginLeft: 12, marginTop: 6, padding: '6px 10px', background: 'rgba(168,85,247,0.1)', borderRadius: 6, borderLeft: '3px solid #a855f7' }}>
                      <div style={{ color: '#c084fc', fontSize: '0.85rem', fontWeight: 600 }}>{idea.title}</div>
                      <div style={{ color: '#ccc', fontSize: '0.85rem' }}>新颖性：{idea.novelty}</div>
                      <div style={{ color: '#aaa', fontSize: '0.8rem' }}>方法：{idea.methodology}</div>
                      <div style={{ color: '#888', fontSize: '0.8rem' }}>可行性：{idea.feasibility} | 预期贡献：{idea.expected_contribution}</div>
                    </div>
                  ))}
                </div>
              )}
              {result.output.innovation_analysis.recommended_approach && (
                <div style={{ marginTop: 8, padding: '6px 10px', background: 'rgba(34,197,94,0.1)', borderRadius: 6, borderLeft: '3px solid #22c55e' }}>
                  <strong style={{ color: '#4ade80' }}>推荐方案：</strong>
                  <span style={{ color: '#ccc', fontSize: '0.85rem' }}> {result.output.innovation_analysis.recommended_approach}</span>
                </div>
              )}
            </div>
          )}

          {result?.output?.task_summary && (
            <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4">
              <div className="text-[0.9375rem] text-[#3498db] font-bold mb-2">📊 任务总结报告</div>
              {result.output.task_summary.research_summary && (
                <div style={{ marginBottom: 8, color: '#ccc', fontSize: '0.9rem' }}>
                  <strong style={{ color: '#E2E8F0' }}>研究回顾：</strong>{result.output.task_summary.research_summary}
                </div>
              )}
              {result.output.task_summary.paper_quality && (
                <div style={{ marginBottom: 8, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                  <div style={{ padding: '4px 10px', background: 'rgba(59,130,246,0.15)', borderRadius: 6 }}>
                    <span style={{ color: '#93c5fd', fontSize: '0.8rem' }}>论文质量 </span>
                    <span style={{ color: '#60a5fa', fontWeight: 700 }}>{result.output.task_summary.paper_quality.overall_score}/100</span>
                  </div>
                  {result.output.task_summary.paper_quality.strengths?.length > 0 && (
                    <div style={{ color: '#4ade80', fontSize: '0.8rem' }}>优势：{result.output.task_summary.paper_quality.strengths.join('、')}</div>
                  )}
                  {result.output.task_summary.paper_quality.weaknesses?.length > 0 && (
                    <div style={{ color: '#f87171', fontSize: '0.8rem' }}>不足：{result.output.task_summary.paper_quality.weaknesses.join('、')}</div>
                  )}
                </div>
              )}
              {result.output.task_summary.lessons_learned?.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <strong style={{ color: '#E2E8F0' }}>经验教训：</strong>
                  {result.output.task_summary.lessons_learned.map((l: any, i: number) => (
                    <div key={i} style={{ marginLeft: 12, marginTop: 4, fontSize: '0.85rem' }}>
                      <span style={{
                        padding: '1px 5px', borderRadius: 3, fontSize: '0.7rem',
                        background: 'rgba(234,179,8,0.15)', color: '#facc15', marginRight: 6,
                      }}>
                        {l.category}
                      </span>
                      <span style={{ color: '#ccc' }}>{l.content}</span>
                    </div>
                  ))}
                </div>
              )}
              {result.output.task_summary.recommendations?.length > 0 && (
                <div>
                  <strong style={{ color: '#E2E8F0' }}>建议：</strong>
                  {result.output.task_summary.recommendations.map((r: string, i: number) => (
                    <div key={i} style={{ marginLeft: 12, color: '#aaa', fontSize: '0.85rem' }}>• {r}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {!loading && activeTab === 'peer_review' && (
        <div className="flex-1 overflow-y-auto max-h-[520px] flex flex-col gap-[0.8rem]">
          {taskState.state?.peerReview ? (
            <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4">
              <div className="text-[0.9375rem] text-[#3498db] font-bold mb-2">🔍 同行评议结果</div>
              <div className="flex gap-4 py-[0.6rem] border-b border-[#1E293B] items-start flex-wrap">
                <span className="text-[0.78rem] text-[#475569] min-w-[80px] font-semibold">总体评分</span>
                <span className="text-[0.9375rem] text-[#CBD5E1] flex-1 break-all">{'★'.repeat(Math.round(taskState.state.peerReview.overallScore))}{'☆'.repeat(5 - Math.round(taskState.state.peerReview.overallScore))} ({taskState.state.peerReview.overallScore}/5)</span>
              </div>
              <div className="flex gap-4 py-[0.6rem] border-b border-[#1E293B] items-start flex-wrap">
                <span className="text-[0.78rem] text-[#475569] min-w-[80px] font-semibold">推荐结论</span>
                <span className="text-[0.9375rem] text-[#CBD5E1] flex-1 break-all">
                  {taskState.state.peerReview.recommendation === 'accept' && '✅ 接收'}
                  {taskState.state.peerReview.recommendation === 'revise' && '⚠️ 修订'}
                  {taskState.state.peerReview.recommendation === 'reject' && '❌ 拒稿'}
                </span>
              </div>
              <PeerReviewDetails taskId={taskId} />
            </div>
          ) : (
            <div className="text-center p-[2rem] text-[#475569] text-[0.9375rem]">暂无同行评议数据。任务完成后若触发了同行评议，将在此显示。</div>
          )}
          {taskState.state?.name === 'completed' && meta?.status === 'completed' && (
            <CameraReadyDownload taskId={taskId} templateId={taskState.state?.templateId || meta?.template || 'math_modeling'} />
          )}
        </div>
      )}

      {!loading && activeTab === 'info' && meta && (
        <div className="flex-1 overflow-y-auto max-h-[520px] p-[0.5rem] bg-[rgba(0,0,0,0.2)] rounded-[8px]">
          <div className="flex gap-4 py-[0.6rem] border-b border-[#1E293B] items-start flex-wrap">
            <span className="text-[0.78rem] text-[#475569] min-w-[80px] font-semibold">任务ID</span>
            <code className="text-[0.9375rem] text-[#CBD5E1] flex-1 break-all">{taskId}</code>
          </div>
          <div className="flex gap-4 py-[0.6rem] border-b border-[#1E293B] items-start flex-wrap">
            <span className="text-[0.78rem] text-[#475569] min-w-[80px] font-semibold">状态</span>
            <span className="text-[0.9375rem] text-[#CBD5E1] flex-1 break-all">{meta.status}</span>
          </div>
          <div className="flex gap-4 py-[0.6rem] border-b border-[#1E293B] items-start flex-wrap">
            <span className="text-[0.78rem] text-[#475569] min-w-[80px] font-semibold">进度</span>
            <span className="text-[0.9375rem] text-[#CBD5E1] flex-1 break-all">{meta.progress_percentage || 0}%</span>
          </div>
          <div className="flex gap-4 py-[0.6rem] border-b border-[#1E293B] items-start flex-wrap">
            <span className="text-[0.78rem] text-[#475569] min-w-[80px] font-semibold">当前步骤</span>
            <span className="text-[0.9375rem] text-[#CBD5E1] flex-1 break-all">{meta.current_step || '无'}</span>
          </div>

          {(meta.status === 'completed' || meta.status === 'failed' || cancelled) && (
            <div className="mt-6 pt-4 border-t border-[#334155]">
              <div className="text-[0.95rem] text-[#f39c12] font-bold mb-[0.8rem]">📝 任务反馈</div>
              {feedbackSent ? (
                <div className="text-[#2ecc71] text-[0.9375rem] p-[0.8rem] bg-[rgba(74,222,128,0.15)] rounded-[6px] text-center">反馈已提交，感谢！</div>
              ) : (
                <>
                  <div className="flex flex-col gap-[0.3rem] mb-[0.8rem]">
                    <label className="text-[0.875rem] text-[#94A3B8]">整体评分</label>
                    <select
                      className="p-[0.5rem] bg-[rgba(0,0,0,0.3)] border border-[#475569] rounded-[6px] text-[#e0e0e0] text-[0.9375rem] font-[inherit]"
                      value={feedback.overall}
                      onChange={(e) => setFeedback({ ...feedback, overall: parseInt(e.target.value) })}
                    >
                      {[5, 4, 3, 2, 1].map((s) => (
                        <option key={s} value={s}>{s} 星</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex flex-col gap-[0.3rem] mb-[0.8rem]">
                    <label className="text-[0.875rem] text-[#94A3B8]">类别</label>
                    <select
                      className="p-[0.5rem] bg-[rgba(0,0,0,0.3)] border border-[#475569] rounded-[6px] text-[#e0e0e0] text-[0.9375rem] font-[inherit]"
                      value={feedback.category}
                      onChange={(e) => setFeedback({ ...feedback, category: e.target.value })}
                    >
                      <option value="method_selection">方法选择</option>
                      <option value="modeling">建模</option>
                      <option value="solving">求解</option>
                      <option value="writing">写作</option>
                      <option value="data_processing">数据处理</option>
                    </select>
                  </div>
                  <div className="flex flex-col gap-[0.3rem] mb-[0.8rem]">
                    <label className="text-[0.875rem] text-[#94A3B8]">建议/备注</label>
                    <textarea
                      className="p-[0.5rem] bg-[rgba(0,0,0,0.3)] border border-[#475569] rounded-[6px] text-[#e0e0e0] text-[0.9375rem] font-[inherit] min-h-[80px] resize-y"
                      value={feedback.comment}
                      onChange={(e) => setFeedback({ ...feedback, comment: e.target.value })}
                      placeholder="描述本次任务中有效的方法或需要改进的地方..."
                    />
                  </div>
                  <button
                    className="py-[0.5rem] px-4 bg-[#2DD4BF] border-none rounded-[6px] text-[#F8FAFC] cursor-pointer text-[0.9375rem] font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                    onClick={handleSubmitFeedback}
                    disabled={submittingFeedback}
                  >
                    {submittingFeedback ? '提交中...' : '提交反馈'}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PeerReviewDetails({ taskId }: { taskId: string }) {
  const [details, setDetails] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const res = await fetch(apiBase() + '/tasks/' + taskId + '/result');
        if (res.ok) {
          const data = await res.json();
          const review = data?.output?.peer_review_agent || data?.output?.final_peer_review || data?.peer_review_agent;
          setDetails(review);
        }
      } catch {}
      setLoading(false);
    };
    load();
  }, [taskId]);

  if (loading) return <div className="text-center p-[2rem] text-[#475569] text-[0.9375rem]">加载评议详情...</div>;
  if (!details) return <div className="text-center p-[2rem] text-[#475569] text-[0.9375rem]">无详细评议数据</div>;

  const scores = details.scores || {};
  const comments = details.comments || {};
  const edits = details.suggested_edits || [];

  return (
    <div>
      {Object.keys(scores).length > 0 && (
        <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4">
          <div className="text-[0.9375rem] text-[#3498db] font-bold mb-2">分项评分</div>
          {Object.entries(scores).map(([k, v]: [string, any]) => (
            <div key={k} className="flex gap-4 py-[0.6rem] border-b border-[#1E293B] items-start flex-wrap">
              <span className="text-[0.78rem] text-[#475569] min-w-[80px] font-semibold">{k}</span>
              <span className="text-[0.9375rem] text-[#CBD5E1] flex-1 break-all">{v}/5</span>
            </div>
          ))}
        </div>
      )}
      {(comments.major?.length > 0 || comments.minor?.length > 0) && (
        <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4">
          <div className="text-[0.9375rem] text-[#3498db] font-bold mb-2">评审意见</div>
          {(comments.major || []).map((c: string, i: number) => (
            <div key={`major-${i}`} className="pl-[0.5rem] text-[#94A3B8]">• <strong>Major:</strong> {c}</div>
          ))}
          {(comments.minor || []).map((c: string, i: number) => (
            <div key={`minor-${i}`} className="pl-[0.5rem] text-[#94A3B8]">• Minor: {c}</div>
          ))}
        </div>
      )}
      {edits.length > 0 && (
        <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4">
          <div className="text-[0.9375rem] text-[#3498db] font-bold mb-2">建议编辑</div>
          {edits.map((ed: any, i: number) => (
            <div key={i} className="pl-[0.5rem] text-[#94A3B8]">
              • {ed.location ? `[${ed.location}] ` : ''}{ed.suggestion || ed}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CameraReadyDownload({ taskId, templateId }: { taskId: string; templateId: string }) {
  const [status, setStatus] = useState<'idle' | 'building' | 'ready' | 'error'>('idle');
  const [pkg, setPkg] = useState<any>(null);

  const build = async () => {
    setStatus('building');
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/camera-ready', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template_id: templateId }),
      });
      const data = await res.json();
      if (res.ok) {
        setPkg(data);
        setStatus('ready');
      } else {
        setStatus('error');
      }
    } catch {
      setStatus('error');
    }
  };

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch(apiBase() + '/tasks/' + taskId + '/camera-ready');
        if (res.ok) {
          const data = await res.json();
          if (data.exists) {
            setPkg(data);
            setStatus('ready');
          }
        }
      } catch {}
    };
    check();
  }, [taskId]);

  return (
    <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4">
      <div className="text-[0.9375rem] text-[#3498db] font-bold mb-2">📦 Camera-Ready 下载</div>
      {status === 'idle' && (
        <button className="py-[0.35rem] px-[0.9rem] bg-[rgba(74,222,128,0.15)] border border-[rgba(74,222,128,0.15)] rounded-[6px] text-[#2ecc71] text-[0.78rem] cursor-pointer transition-all duration-200 hover:bg-[rgba(74,222,128,0.15)]" onClick={build}>生成并下载 zip</button>
      )}
      {status === 'building' && <div>打包中...</div>}
      {status === 'error' && <div>打包失败，请稍后重试。</div>}
      {status === 'ready' && pkg?.zip_path && (
        <div>
          <a href={apiBase() + '/tasks/' + taskId + '/camera-ready/download?path=' + encodeURIComponent(pkg.zip_path)} download>
            ⬇️ 下载 camera-ready.zip
          </a>
          {pkg.verification?.success === false && (
            <div style={{ color: '#e67e22', marginTop: 4 }}>⚠️ 编译验证未通过，请检查 LaTeX 源文件。</div>
          )}
        </div>
      )}
    </div>
  );
}
