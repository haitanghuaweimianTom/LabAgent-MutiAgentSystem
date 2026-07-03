'use client';

import { useState, useEffect } from 'react';
import styles from './TaskDetail.module.css';
import PaperPreview from './PaperPreview';
import AlgorithmRecommend from './AlgorithmRecommend';
import PaperList from './PaperList';
import { useTaskState } from '../hooks/useTaskState';

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

const TEAM_COLORS: Record<string, string> = {
  coordinator: '#e74c3c',
  research_agent: '#3498db',
  data_agent: '#9b59b6',
  analyzer_agent: '#f39c12',
  modeler_agent: '#27ae60',
  algorithm_engineer_agent: '#16a085',
  financial_analyst_agent: '#d4ac0d',
  solver_agent: '#e67e22',
  writer_agent: '#1abc9c',
  peer_review_agent: '#8e44ad',
  experimentation_agent: '#2c3e50',
  figure_agent: '#e84393',
  requirement_decomposer: '#00b894',
  innovation_agent: '#6c5ce7',
  summary_agent: '#fdcb6e',
  system: '#95a5a6',
  user: '#2ecc71',
};

const TEAM_LABELS: Record<string, string> = {
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
  requirement_decomposer: '需求分解器',
  innovation_agent: '创新发现专家',
  summary_agent: '总结专家',
  system: '系统',
  user: '你',
};

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

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
      // 传递原始任务的 template/workflow_type/mode，确保 rerun 保留用户选择
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
      className={msg.type === 'result' ? styles.msgResult : styles.msg}
      style={{ borderLeftColor: TEAM_COLORS[msg.sender] || '#666' }}
    >
      <div className={styles.msgHeader}>
        <span style={{ color: TEAM_COLORS[msg.sender] || '#666', fontWeight: 600 }}>{msg.sender_label}</span>
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
  );

  // Extract algorithms from result if present
  const algorithms = result?.output?.algorithms || result?.output?.modeler_agent?.algorithms || [];
  const latexCode = result?.output?.latex_code || result?.latex_code || '';
  const abstract = result?.output?.abstract || result?.abstract || '';
  const keywords = result?.output?.keywords || result?.keywords || [];
  const markdown = result?.output?.markdown || result?.output?.paper || '';

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.title}>📄 任务详情: {taskId}</span>
        <div className={styles.actions}>
          {meta?.status === 'running' && !cancelled && (
            <button className={styles.cancelBtn} onClick={handleCancel} disabled={cancelling}>
              {cancelling ? '取消中...' : '⏹ 取消任务'}
            </button>
          )}
          <button className={styles.exportBtn} onClick={handleExport} disabled={exporting}>
            {exporting ? '导出中...' : '💾 导出到桌面'}
          </button>
          {canRerun && (
            <button className={styles.exportBtn} onClick={handleRerun} disabled={rerunning}>
              {rerunning ? '创建中...' : '🔄 重新执行'}
            </button>
          )}
          <button className={styles.deleteBtn} onClick={onDelete}>🗑️ 删除</button>
        </div>
      </div>

      {/* 实时进度条 */}
      {taskState.state && taskState.state.name !== 'completed' && taskState.state.name !== 'failed' && (
        <div className={styles.progressBar}>
          <div
            className={styles.progressFill}
            style={{ width: `${taskState.state.progressPercentage}%` }}
          />
          <span className={styles.progressText}>
            {taskState.state.progressPercentage}% · {taskState.state.currentStep || '运行中...'}
          </span>
        </div>
      )}

      <div className={styles.tabs}>
        {(['messages', 'result', 'peer_review', 'info'] as const).map(t => (
          <button
            key={t}
            className={`${styles.tab} ${activeTab === t ? styles.tabActive : ''}`}
            onClick={() => setActiveTab(t)}
          >
            {t === 'messages' && '💬 讨论记录'}
            {t === 'result' && '📊 结果'}
            {t === 'peer_review' && '🔍 同行评议'}
            {t === 'info' && 'ℹ️ 详情'}
          </button>
        ))}
      </div>

      {loading && <div className={styles.empty}>加载中...</div>}

      {!loading && activeTab === 'messages' && (
        <div className={styles.messagesPanel}>
          {messages.length === 0 ? <div className={styles.empty}>暂无讨论记录</div> : messages.map(renderMsg)}
        </div>
      )}

      {!loading && activeTab === 'result' && (
        <div className={styles.resultPanel}>
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
            <div className={styles.section}>
              <div className={styles.sectionTitle}>📊 数据分析</div>
              {result.output.analyses.map((a: any, i: number) => (
                <div key={i} className={styles.analysisCard}>
                  <strong>{a.file_name}</strong>
                  <span> {a.shape?.[0]}行 × {a.shape?.[1]}列</span>
                  <div>{a.data_quality?.missing_rate === 0 ? '✓ 无缺失值' : `⚠ 缺失率 ${a.data_quality?.missing_rate}`}</div>
                  {(a.insights || []).map((ins: string, j: number) => (
                    <div key={j} className={styles.listItem}>• {ins}</div>
                  ))}
                </div>
              ))}
            </div>
          )}

          {/* 需求分解计划 */}
          {result?.output?.requirement_plan && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>📋 需求分解计划</div>
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

          {/* 创新发现分析 */}
          {result?.output?.innovation_analysis && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>💡 创新发现分析</div>
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

          {/* 任务总结报告 */}
          {result?.output?.task_summary && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>📊 任务总结报告</div>
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
        <div className={styles.resultPanel}>
          {taskState.state?.peerReview ? (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>🔍 同行评议结果</div>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>总体评分</span>
                <span className={styles.infoValue}>{'★'.repeat(Math.round(taskState.state.peerReview.overallScore))}{'☆'.repeat(5 - Math.round(taskState.state.peerReview.overallScore))} ({taskState.state.peerReview.overallScore}/5)</span>
              </div>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>推荐结论</span>
                <span className={styles.infoValue}>
                  {taskState.state.peerReview.recommendation === 'accept' && '✅ 接收'}
                  {taskState.state.peerReview.recommendation === 'revise' && '⚠️ 修订'}
                  {taskState.state.peerReview.recommendation === 'reject' && '❌ 拒稿'}
                </span>
              </div>
              <PeerReviewDetails taskId={taskId} />
            </div>
          ) : (
            <div className={styles.empty}>暂无同行评议数据。任务完成后若触发了同行评议，将在此显示。</div>
          )}
          {taskState.state?.name === 'completed' && meta?.status === 'completed' && (
            <CameraReadyDownload taskId={taskId} templateId={taskState.state?.templateId || meta?.template || 'math_modeling'} />
          )}
        </div>
      )}

      {!loading && activeTab === 'info' && meta && (
        <div className={styles.infoPanel}>
          <div className={styles.infoRow}>
            <span className={styles.infoLabel}>任务ID</span>
            <code className={styles.infoValue}>{taskId}</code>
          </div>
          <div className={styles.infoRow}>
            <span className={styles.infoLabel}>状态</span>
            <span className={styles.infoValue}>{meta.status}</span>
          </div>
          <div className={styles.infoRow}>
            <span className={styles.infoLabel}>进度</span>
            <span className={styles.infoValue}>{meta.progress_percentage || 0}%</span>
          </div>
          <div className={styles.infoRow}>
            <span className={styles.infoLabel}>当前步骤</span>
            <span className={styles.infoValue}>{meta.current_step || '无'}</span>
          </div>

          {(meta.status === 'completed' || meta.status === 'failed' || cancelled) && (
            <div className={styles.feedbackSection}>
              <div className={styles.feedbackTitle}>📝 任务反馈</div>
              {feedbackSent ? (
                <div className={styles.feedbackSent}>反馈已提交，感谢！</div>
              ) : (
                <>
                  <div className={styles.feedbackRow}>
                    <label>整体评分</label>
                    <select
                      value={feedback.overall}
                      onChange={(e) => setFeedback({ ...feedback, overall: parseInt(e.target.value) })}
                    >
                      {[5, 4, 3, 2, 1].map((s) => (
                        <option key={s} value={s}>{s} 星</option>
                      ))}
                    </select>
                  </div>
                  <div className={styles.feedbackRow}>
                    <label>类别</label>
                    <select
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
                  <div className={styles.feedbackRow}>
                    <label>建议/备注</label>
                    <textarea
                      value={feedback.comment}
                      onChange={(e) => setFeedback({ ...feedback, comment: e.target.value })}
                      placeholder="描述本次任务中有效的方法或需要改进的地方..."
                    />
                  </div>
                  <button
                    className={styles.feedbackBtn}
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

  if (loading) return <div className={styles.empty}>加载评议详情...</div>;
  if (!details) return <div className={styles.empty}>无详细评议数据</div>;

  const scores = details.scores || {};
  const comments = details.comments || {};
  const edits = details.suggested_edits || [];

  return (
    <div>
      {Object.keys(scores).length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>分项评分</div>
          {Object.entries(scores).map(([k, v]: [string, any]) => (
            <div key={k} className={styles.infoRow}>
              <span className={styles.infoLabel}>{k}</span>
              <span className={styles.infoValue}>{v}/5</span>
            </div>
          ))}
        </div>
      )}
      {(comments.major?.length > 0 || comments.minor?.length > 0) && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>评审意见</div>
          {(comments.major || []).map((c: string, i: number) => (
            <div key={`major-${i}`} className={styles.listItem}>• <strong>Major:</strong> {c}</div>
          ))}
          {(comments.minor || []).map((c: string, i: number) => (
            <div key={`minor-${i}`} className={styles.listItem}>• Minor: {c}</div>
          ))}
        </div>
      )}
      {edits.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>建议编辑</div>
          {edits.map((ed: any, i: number) => (
            <div key={i} className={styles.listItem}>
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
    <div className={styles.section}>
      <div className={styles.sectionTitle}>📦 Camera-Ready 下载</div>
      {status === 'idle' && (
        <button className={styles.exportBtn} onClick={build}>生成并下载 zip</button>
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
