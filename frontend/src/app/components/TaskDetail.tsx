'use client';

import { useState, useEffect } from 'react';
import PaperPreview from './PaperPreview';
import AlgorithmRecommend from './AlgorithmRecommend';
import PaperList from './PaperList';
import { useTaskState } from '../hooks/useTaskState';
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
  const [userInput, setUserInput] = useState('');
  const [sendingMsg, setSendingMsg] = useState(false);

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

  // 历史详情页向已结束的任务追加消息/追问。后端 post_user_message 会存入聊天室，
  // 若任务仍在等待态则 resume，否则触发被 @ 的 agent 用 LLM 回应（事后追问）。
  const reloadMessages = async () => {
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/messages');
      if (res.ok) {
        const msgs = await res.json();
        setMessages(msgs.map((m: any) => ({
          id: m.id, sender: m.sender,
          sender_label: m.sender_label || TEAM_LABELS[m.sender] || m.sender,
          content: m.content, type: m.type || 'text', timestamp: m.timestamp,
        })));
      }
    } catch {}
  };

  const handleSendMessage = async () => {
    const content = userInput.trim();
    if (!content) return;
    setSendingMsg(true);
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      if (res.ok) {
        setUserInput('');
        // 稍等后端处理完（agent 回应是异步 create_task），再拉取新消息
        setTimeout(() => { reloadMessages(); }, 800);
      } else {
        alert('发送失败');
      }
    } catch { alert('发送失败'); } finally { setSendingMsg(false); }
  };

  const handleInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendMessage(); }
  };

  const renderMsg = (msg: Message) => (
    <div
      key={msg.id}
      className={cn(
        'px-5 py-3 mb-2 rounded-md border-l-2',
        msg.type === 'result'
          ? 'bg-primary/10 border-primary'
          : msg.type === 'user_input'
            ? 'bg-primary/10 border-primary'
            : 'bg-card border-border'
      )}
    >
      <div className="flex justify-between mb-2 text-sm items-center">
        <span className="font-semibold text-foreground">{msg.sender_label}</span>
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
  );

  const algorithms = result?.output?.algorithms || result?.output?.modeler_agent?.algorithms || [];
  const latexCode = result?.output?.latex_code || result?.latex_code || '';
  const abstract = result?.output?.abstract || result?.abstract || '';
  const keywords = result?.output?.keywords || result?.keywords || [];
  const markdown = result?.output?.markdown || result?.output?.paper || '';

  return (
    <div data-design-id="history:detail-card" className="flex flex-col gap-3 h-full">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <span data-design-id="history:detail-title" className="text-lg text-foreground font-semibold">📄 任务详情: {taskId}</span>
        <div data-design-id="history:detail-actions" className="flex gap-3">
          {meta?.status === 'running' && !cancelled && (
            <button data-design-id="history:btn-cancel" className="inline-flex items-center justify-center gap-3 min-h-[36px] py-1.5 px-6 bg-error/10 text-error border border-error/20 rounded-md text-sm cursor-pointer transition-colors hover:bg-error/15 disabled:opacity-50 disabled:cursor-not-allowed shrink-0" onClick={handleCancel} disabled={cancelling}>
              {cancelling ? '取消中...' : '⏹ 取消任务'}
            </button>
          )}
          <button data-design-id="history:btn-export" className="inline-flex items-center justify-center gap-3 min-h-[40px] py-2 px-8 bg-primary text-primary-foreground rounded-lg text-sm cursor-pointer transition-opacity hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed shrink-0" onClick={handleExport} disabled={exporting}>
            {exporting ? '导出中...' : '💾 导出到桌面'}
          </button>
          {canRerun && (
            <button data-design-id="history:btn-rerun" className="inline-flex items-center justify-center gap-3 min-h-[40px] py-2 px-8 bg-primary text-primary-foreground rounded-lg text-sm cursor-pointer transition-opacity hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed shrink-0" onClick={handleRerun} disabled={rerunning}>
              {rerunning ? '创建中...' : '🔄 重新执行'}
            </button>
          )}
          <button data-design-id="history:btn-delete" className="inline-flex items-center justify-center gap-3 min-h-[36px] py-1.5 px-6 bg-error/10 text-error border border-error/20 rounded-md text-sm cursor-pointer transition-colors hover:bg-error/15 shrink-0" onClick={onDelete}>🗑️ 删除</button>
        </div>
      </div>

      {taskState.state && taskState.state.name !== 'completed' && taskState.state.name !== 'failed' && (
        <div className="flex flex-col gap-3">
          <div className="flex justify-between items-center text-xs">
            <span className="text-muted-foreground truncate" title={taskState.state.currentStep || ''}>
              {taskState.state.currentStep || '运行中...'}
            </span>
            <span className="text-foreground font-semibold tabular-nums shrink-0 ml-2">
              {taskState.state.progressPercentage}%
            </span>
          </div>
          <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-[width] duration-500 ease-out"
              style={{ width: `${taskState.state.progressPercentage}%` }}
            />
          </div>
        </div>
      )}

      <div data-design-id="history:tab-row" className="flex gap-3 border-b border-border pb-2">
        {(['messages', 'result', 'peer_review', 'info'] as const).map(t => (
          <button
            key={t}
            className={cn(
              'py-1.5 px-5 rounded-md text-sm cursor-pointer transition-colors duration-150 border border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground',
              activeTab === t && 'bg-primary/10 border-primary/20 text-primary'
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

      {loading && <div className="text-center p-[2rem] text-muted-foreground text-sm">加载中...</div>}

      {!loading && activeTab === 'messages' && (
        <div className="flex-1 flex flex-col gap-3">
          <div className="overflow-y-auto max-h-[460px] p-2 bg-muted/50 rounded-md">
            {messages.length === 0 ? <div className="text-center p-[2rem] text-muted-foreground text-sm">暂无讨论记录</div> : messages.map(renderMsg)}
          </div>
          <div className="pt-[0.4rem] border-t border-border">
            <div className="flex gap-3 items-end">
              <textarea
                className="flex-1 py-2 px-[1.2rem] bg-muted border border-border rounded-md text-foreground text-sm resize-none font-[inherit] leading-[1.5] focus:outline-none focus:border-primary placeholder:text-muted-foreground"
                placeholder="向团队追加消息或追问（@Agent名称 可指定专家）..."
                value={userInput}
                onChange={e => setUserInput(e.target.value)}
                onKeyDown={handleInputKeyDown}
                rows={2}
                disabled={sendingMsg}
              />
              <button
                className="py-2.5 px-7 bg-primary text-primary-foreground border-none rounded-md text-sm font-semibold cursor-pointer transition-opacity duration-150 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-90"
                onClick={handleSendMessage}
                disabled={!userInput.trim() || sendingMsg}
              >
                {sendingMsg ? '...' : '发送'}
              </button>
            </div>
            <div className="mt-1 text-xs text-muted-foreground text-center">Enter 发送 · Shift+Enter 换行 · 你的消息会出现在讨论记录中</div>
          </div>
        </div>
      )}

      {!loading && activeTab === 'result' && (
        <div className="flex-1 overflow-y-auto max-h-[520px] flex flex-col gap-3">
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
            <div className="bg-card border border-border rounded-lg px-6 py-4">
              <div className="text-sm text-primary font-bold mb-2">📊 数据分析</div>
              {result.output.analyses.map((a: any, i: number) => (
                <div key={i} className="bg-muted rounded-md px-5 py-3 mb-1.5 text-sm text-muted-foreground border border-border">
                  <strong className="text-foreground">{a.file_name}</strong>
                  <span> {a.shape?.[0]}行 × {a.shape?.[1]}列</span>
                  <div>{a.data_quality?.missing_rate === 0 ? '✓ 无缺失值' : `⚠ 缺失率 ${a.data_quality?.missing_rate}`}</div>
                  {(a.insights || []).map((ins: string, j: number) => (
                    <div key={j} className="pl-[0.5rem] text-muted-foreground">• {ins}</div>
                  ))}
                </div>
              ))}
            </div>
          )}

          {result?.output?.requirement_plan && (
            <div className="bg-card border border-border rounded-lg px-6 py-4">
              <div className="text-sm text-primary font-semibold mb-2">📋 需求分解计划</div>
              <div className="mb-2 text-primary font-medium">
                {result.output.requirement_plan.research_goal}
              </div>
              {result.output.requirement_plan.background && (
                <div className="mb-2 text-sm text-muted-foreground">
                  {result.output.requirement_plan.background}
                </div>
              )}
              {result.output.requirement_plan.key_questions?.length > 0 && (
                <div className="mb-2">
                  <strong className="text-foreground">核心问题：</strong>
                  {result.output.requirement_plan.key_questions.map((q: string, i: number) => (
                    <div key={i} className="ml-3 text-sm text-muted-foreground">• {q}</div>
                  ))}
                </div>
              )}
              {result.output.requirement_plan.subtasks?.length > 0 && (
                <div>
                  <strong className="text-foreground">子任务：</strong>
                  {result.output.requirement_plan.subtasks.map((t: any, i: number) => (
                    <div key={i} className="flex gap-3 items-center ml-3 mt-1">
                      <span className={cn(
                        'px-1.5 py-0.5 rounded text-xs font-medium',
                        t.priority === 'high' ? 'bg-error/15 text-error' : t.priority === 'medium' ? 'bg-warning/15 text-warning' : 'bg-success/15 text-success'
                      )}>
                        {t.priority}
                      </span>
                      <span className="text-sm text-foreground">{t.description}</span>
                      <span className="text-xs text-muted-foreground">→ {t.suggested_agent}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {result?.output?.innovation_analysis && (
            <div className="bg-card border border-border rounded-lg px-6 py-4">
              <div className="text-sm text-primary font-semibold mb-2">💡 创新发现分析</div>
              {result.output.innovation_analysis.research_gaps?.length > 0 && (
                <div className="mb-3">
                  <strong className="text-foreground">研究空白：</strong>
                  {result.output.innovation_analysis.research_gaps.map((g: any, i: number) => (
                    <div key={i} className="ml-3 mt-1.5 px-4 py-1.5 bg-primary/10 rounded-md border-l-2 border-primary">
                      <div className="text-sm font-medium text-primary">
                        Gap #{g.gap_id} <span className={g.importance === 'high' ? 'text-error' : 'text-warning'}>({g.importance})</span>
                      </div>
                      <div className="text-sm text-foreground">{g.description}</div>
                      {g.opportunity && <div className="text-xs text-muted-foreground mt-0.5">机会：{g.opportunity}</div>}
                    </div>
                  ))}
                </div>
              )}
              {result.output.innovation_analysis.innovation_ideas?.length > 0 && (
                <div>
                  <strong className="text-foreground">创新方案：</strong>
                  {result.output.innovation_analysis.innovation_ideas.map((idea: any, i: number) => (
                    <div key={i} className="ml-3 mt-1.5 px-4 py-1.5 bg-muted rounded-md border-l-2 border-foreground/30">
                      <div className="text-sm font-medium text-foreground">{idea.title}</div>
                      <div className="text-sm text-foreground">新颖性：{idea.novelty}</div>
                      <div className="text-xs text-muted-foreground">方法：{idea.methodology}</div>
                      <div className="text-xs text-muted-foreground">可行性：{idea.feasibility} | 预期贡献：{idea.expected_contribution}</div>
                    </div>
                  ))}
                </div>
              )}
              {result.output.innovation_analysis.recommended_approach && (
                <div className="mt-2 px-4 py-1.5 bg-success/10 rounded-md border-l-2 border-success">
                  <strong className="text-success">推荐方案：</strong>
                  <span className="text-sm text-foreground"> {result.output.innovation_analysis.recommended_approach}</span>
                </div>
              )}
            </div>
          )}

          {result?.output?.task_summary && (
            <div className="bg-card border border-border rounded-lg px-6 py-4">
              <div className="text-sm text-primary font-semibold mb-2">📊 任务总结报告</div>
              {result.output.task_summary.research_summary && (
                <div className="mb-2 text-sm text-foreground">
                  <strong className="text-foreground">研究回顾：</strong>{result.output.task_summary.research_summary}
                </div>
              )}
              {result.output.task_summary.paper_quality && (
                <div className="mb-2 flex gap-4 flex-wrap">
                  <div className="px-4 py-1 bg-primary/10 rounded-md">
                    <span className="text-xs text-primary">论文质量 </span>
                    <span className="text-primary font-bold">{result.output.task_summary.paper_quality.overall_score}/100</span>
                  </div>
                  {result.output.task_summary.paper_quality.strengths?.length > 0 && (
                    <div className="text-xs text-success">优势：{result.output.task_summary.paper_quality.strengths.join('、')}</div>
                  )}
                  {result.output.task_summary.paper_quality.weaknesses?.length > 0 && (
                    <div className="text-xs text-error">不足：{result.output.task_summary.paper_quality.weaknesses.join('、')}</div>
                  )}
                </div>
              )}
              {result.output.task_summary.lessons_learned?.length > 0 && (
                <div className="mb-2">
                  <strong className="text-foreground">经验教训：</strong>
                  {result.output.task_summary.lessons_learned.map((l: any, i: number) => (
                    <div key={i} className="ml-3 mt-1 text-sm">
                      <span className="px-1.5 py-0.5 rounded-sm text-xs bg-warning/15 text-warning mr-1.5">
                        {l.category}
                      </span>
                      <span className="text-foreground">{l.content}</span>
                    </div>
                  ))}
                </div>
              )}
              {result.output.task_summary.recommendations?.length > 0 && (
                <div>
                  <strong className="text-foreground">建议：</strong>
                  {result.output.task_summary.recommendations.map((r: string, i: number) => (
                    <div key={i} className="ml-3 text-sm text-muted-foreground">• {r}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {!loading && activeTab === 'peer_review' && (
        <div className="flex-1 overflow-y-auto max-h-[520px] flex flex-col gap-3">
          {taskState.state?.peerReview ? (
            <div className="bg-card border border-border rounded-lg px-6 py-4">
              <div className="text-sm text-primary font-bold mb-2">🔍 同行评议结果</div>
              <div className="flex gap-4 py-2.5 border-b border-border items-start flex-wrap">
                <span className="text-sm text-muted-foreground min-w-[80px] font-semibold">总体评分</span>
                <span className="text-sm text-foreground flex-1 break-all">{'★'.repeat(Math.round(taskState.state.peerReview.overallScore))}{'☆'.repeat(5 - Math.round(taskState.state.peerReview.overallScore))} ({taskState.state.peerReview.overallScore}/5)</span>
              </div>
              <div className="flex gap-4 py-2.5 border-b border-border items-start flex-wrap">
                <span className="text-sm text-muted-foreground min-w-[80px] font-semibold">推荐结论</span>
                <span className="text-sm text-foreground flex-1 break-all">
                  {taskState.state.peerReview.recommendation === 'accept' && '✅ 接收'}
                  {taskState.state.peerReview.recommendation === 'revise' && '⚠️ 修订'}
                  {taskState.state.peerReview.recommendation === 'reject' && '❌ 拒稿'}
                </span>
              </div>
              <PeerReviewDetails taskId={taskId} />
            </div>
          ) : (
            <div className="text-center p-[2rem] text-muted-foreground text-sm">暂无同行评议数据。任务完成后若触发了同行评议，将在此显示。</div>
          )}
          {taskState.state?.name === 'completed' && meta?.status === 'completed' && (
            <CameraReadyDownload taskId={taskId} templateId={taskState.state?.templateId || meta?.template || 'math_modeling'} />
          )}
        </div>
      )}

      {!loading && activeTab === 'info' && meta && (
        <div className="flex-1 overflow-y-auto max-h-[520px] p-2 bg-muted/50 rounded-md">
          <div className="flex gap-4 py-2.5 border-b border-border items-start flex-wrap">
            <span className="text-sm text-muted-foreground min-w-[80px] font-semibold">任务ID</span>
            <code className="text-sm text-foreground flex-1 break-all">{taskId}</code>
          </div>
          <div className="flex gap-4 py-2.5 border-b border-border items-start flex-wrap">
            <span className="text-sm text-muted-foreground min-w-[80px] font-semibold">状态</span>
            <span className="text-sm text-foreground flex-1 break-all">{meta.status}</span>
          </div>
          <div className="flex gap-4 py-2.5 border-b border-border items-start flex-wrap">
            <span className="text-sm text-muted-foreground min-w-[80px] font-semibold">进度</span>
            <span className="text-sm text-foreground flex-1 break-all">{meta.progress_percentage || 0}%</span>
          </div>
          <div className="flex gap-4 py-2.5 border-b border-border items-start flex-wrap">
            <span className="text-sm text-muted-foreground min-w-[80px] font-semibold">当前步骤</span>
            <span className="text-sm text-foreground flex-1 break-all">{meta.current_step || '无'}</span>
          </div>

          {(meta.status === 'completed' || meta.status === 'failed' || cancelled) && (
            <div className="mt-6 pt-4 border-t border-border">
              <div className="text-sm text-warning font-bold mb-3">📝 任务反馈</div>
              {feedbackSent ? (
                <div className="text-success text-sm p-3 bg-success/10 rounded-md text-center">反馈已提交，感谢！</div>
              ) : (
                <>
                  <div className="flex flex-col gap-3 mb-3">
                    <label className="text-sm text-muted-foreground">整体评分</label>
                    <select
                      className="px-4 py-2 bg-muted border border-border rounded-md text-foreground text-sm font-[inherit]"
                      value={feedback.overall}
                      onChange={(e) => setFeedback({ ...feedback, overall: parseInt(e.target.value) })}
                    >
                      {[5, 4, 3, 2, 1].map((s) => (
                        <option key={s} value={s}>{s} 星</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex flex-col gap-3 mb-3">
                    <label className="text-sm text-muted-foreground">类别</label>
                    <select
                      className="px-4 py-2 bg-muted border border-border rounded-md text-foreground text-sm font-[inherit]"
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
                  <div className="flex flex-col gap-3 mb-3">
                    <label className="text-sm text-muted-foreground">建议/备注</label>
                    <textarea
                      className="px-4 py-2 bg-muted border border-border rounded-md text-foreground text-sm font-[inherit] min-h-[80px] resize-y"
                      value={feedback.comment}
                      onChange={(e) => setFeedback({ ...feedback, comment: e.target.value })}
                      placeholder="描述本次任务中有效的方法或需要改进的地方..."
                    />
                  </div>
                  <button
                    className="py-2.5 px-7 bg-primary text-primary-foreground border-none rounded-md cursor-pointer text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-90"
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

  if (loading) return <div className="text-center p-[2rem] text-muted-foreground text-sm">加载评议详情...</div>;
  if (!details) return <div className="text-center p-[2rem] text-muted-foreground text-sm">无详细评议数据</div>;

  const scores = details.scores || {};
  const comments = details.comments || {};
  const edits = details.suggested_edits || [];

  return (
    <div>
      {Object.keys(scores).length > 0 && (
        <div className="bg-card border border-border rounded-lg px-6 py-4">
          <div className="text-sm text-primary font-bold mb-2">分项评分</div>
          {Object.entries(scores).map(([k, v]: [string, any]) => (
            <div key={k} className="flex gap-4 py-2.5 border-b border-border items-start flex-wrap">
              <span className="text-sm text-muted-foreground min-w-[80px] font-semibold">{k}</span>
              <span className="text-sm text-foreground flex-1 break-all">{v}/5</span>
            </div>
          ))}
        </div>
      )}
      {(comments.major?.length > 0 || comments.minor?.length > 0) && (
        <div className="bg-card border border-border rounded-lg px-6 py-4">
          <div className="text-sm text-primary font-bold mb-2">评审意见</div>
          {(comments.major || []).map((c: string, i: number) => (
            <div key={`major-${i}`} className="pl-[0.5rem] text-muted-foreground">• <strong>Major:</strong> {c}</div>
          ))}
          {(comments.minor || []).map((c: string, i: number) => (
            <div key={`minor-${i}`} className="pl-[0.5rem] text-muted-foreground">• Minor: {c}</div>
          ))}
        </div>
      )}
      {edits.length > 0 && (
        <div className="bg-card border border-border rounded-lg px-6 py-4">
          <div className="text-sm text-primary font-bold mb-2">建议编辑</div>
          {edits.map((ed: any, i: number) => (
            <div key={i} className="pl-[0.5rem] text-muted-foreground">
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
    <div className="bg-card border border-border rounded-lg px-6 py-4">
      <div className="text-sm text-primary font-bold mb-2">📦 Camera-Ready 下载</div>
      {status === 'idle' && (
        <button className="py-1.5 px-5 bg-success/10 border border-success/20 rounded-md text-success text-sm cursor-pointer transition-all duration-200 hover:bg-success/10" onClick={build}>生成并下载 zip</button>
      )}
      {status === 'building' && <div>打包中...</div>}
      {status === 'error' && <div>打包失败，请稍后重试。</div>}
      {status === 'ready' && pkg?.zip_path && (
        <div>
          <a href={apiBase() + '/tasks/' + taskId + '/camera-ready/download?path=' + encodeURIComponent(pkg.zip_path)} download>
            ⬇️ 下载 camera-ready.zip
          </a>
          {pkg.verification?.success === false && (
            <div className="text-warning mt-1">⚠️ 编译验证未通过，请检查 LaTeX 源文件。</div>
          )}
        </div>
      )}
    </div>
  );
}
