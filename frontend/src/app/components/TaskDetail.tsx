'use client';

import { useState, useEffect } from 'react';
import styles from './TaskDetail.module.css';
import PaperPreview from './PaperPreview';
import AlgorithmRecommend from './AlgorithmRecommend';

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

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

function formatTime(iso: string) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString('zh-CN', { hour12: false }); } catch { return iso; }
}

export default function TaskDetail({ taskId, onDelete }: TaskDetailProps) {
  const [activeTab, setActiveTab] = useState<'messages' | 'result' | 'info'>('messages');
  const [messages, setMessages] = useState<Message[]>([]);
  const [result, setResult] = useState<any>(null);
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

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
          <button className={styles.exportBtn} onClick={handleExport} disabled={exporting}>
            {exporting ? '导出中...' : '💾 导出到桌面'}
          </button>
          <button className={styles.deleteBtn} onClick={onDelete}>🗑️ 删除</button>
        </div>
      </div>

      <div className={styles.tabs}>
        {(['messages', 'result', 'info'] as const).map(t => (
          <button
            key={t}
            className={`${styles.tab} ${activeTab === t ? styles.tabActive : ''}`}
            onClick={() => setActiveTab(t)}
          >
            {t === 'messages' && '💬 讨论记录'}
            {t === 'result' && '📊 结果'}
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
        </div>
      )}
    </div>
  );
}
