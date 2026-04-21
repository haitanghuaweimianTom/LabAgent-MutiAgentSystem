'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import styles from './page.module.css';

declare global {
  interface Window {
    __API_BASE__?: string;
  }
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

interface Message {
  id: string;
  sender: string;
  sender_label: string;
  content: string;
  type: string;
  timestamp: string;
}

interface FileInfo {
  name: string;
  size: number;
  type: string;
  shape?: [number, number];
  insights?: string[];
}

interface TaskInfo {
  task_id: string;
  problem_text: string;
  problem_preview: string;
  status: string;
  created_at: string;
  completed_at?: string;
  error?: string;
  total_steps: number;
  progress: number;
  current_step: string;
}

interface TaskResult {
  task_id: string;
  output?: Record<string, any>;
  completed_at?: string;
}

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

function formatTime(iso: string) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false });
  } catch { return iso; }
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: styles.statusCompleted,
    running: styles.statusRunning,
    failed: styles.statusFailed,
    cancelled: styles.statusCancelled,
    unknown: styles.statusUnknown,
  };
  const labels: Record<string, string> = {
    completed: '✅ 已完成',
    running: '🔄 进行中',
    failed: '❌ 失败',
    cancelled: '⚠️ 已取消',
    unknown: '❓ 未知',
  };
  return (
    <span className={`${styles.statusBadge} ${map[status] || styles.statusUnknown}`}>
      {labels[status] || status}
    </span>
  );
}

export default function Home() {
  const [tab, setTab] = useState<'input' | 'chat' | 'files' | 'settings' | 'history'>('input');
  const [problemText, setProblemText] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string>('idle');
  const [progress, setProgress] = useState(0);
  const [messages, setMessages] = useState<Message[]>([]);
  const [eventSource, setEventSource] = useState<EventSource | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [uploading, setUploading] = useState(false);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [newMsgCount, setNewMsgCount] = useState(0);
  const prevMsgCountRef = useRef(0);

  // ========== 历史任务相关 ==========
  const [taskList, setTaskList] = useState<TaskInfo[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [detailTaskId, setDetailTaskId] = useState<string | null>(null);
  const [detailMessages, setDetailMessages] = useState<Message[]>([]);
  const [detailResult, setDetailResult] = useState<TaskResult | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'messages' | 'result' | 'info'>('messages');

  // 自动滚动
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  // ========== 批量选择 ==========
  const [selectedTaskIds, setSelectedTaskIds] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [solveMode, setSolveMode] = useState<'batch' | 'sequential'>('sequential');

  // ========== 暂停/恢复 ==========
  const [paused, setPaused] = useState(false);
  const [pausedData, setPausedData] = useState<any>(null);
  const [editingData, setEditingData] = useState<any>({});
  const [resuming, setResuming] = useState(false);

  const toggleTaskSelection = (tid: string) => {
    setSelectedTaskIds(prev => {
      const next = new Set(prev);
      if (next.has(tid)) next.delete(tid); else next.add(tid);
      return next;
    });
  };

  const handleBatchDelete = async () => {
    if (selectedTaskIds.size === 0) return;
    if (!confirm(`确定删除选中的 ${selectedTaskIds.size} 个任务吗？`)) return;
    setBatchDeleting(true);
    try {
      const res = await fetch(apiBase() + '/tasks/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_ids: Array.from(selectedTaskIds) }),
      });
      const data = await res.json();
      alert(`已删除 ${data.deleted_count} 个任务` + (data.failed_count > 0 ? `，失败 ${data.failed_count} 个` : ''));
      setSelectedTaskIds(new Set());
      loadTaskList();
    } catch {} finally { setBatchDeleting(false); }
  };

  const handleExport = async (tid: string) => {
    setExporting(true);
    try {
      const res = await fetch(apiBase() + '/tasks/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: tid }),
      });
      const data = await res.json();
      if (data.success) {
        alert(`已导出到桌面：\n${data.output_dir}\n\n文件：${data.files.join('\n')}`);
      } else {
        alert('导出失败：' + (data.detail || '未知错误'));
      }
    } catch (e) { alert('导出失败'); } finally { setExporting(false); }
  };

  // ========== 暂停/恢复 ==========
  const handlePause = async () => {
    if (!taskId) return;
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/pause', { method: 'POST' });
      const d = await res.json();
      if (d.status === 'paused') {
        setPaused(true);
        // 获取暂停数据供用户编辑
        const pdRes = await fetch(apiBase() + '/tasks/' + taskId + '/pause-data');
        if (pdRes.ok) {
          const pd = await pdRes.json();
          setPausedData(pd.pause_data);
        }
        alert('任务已暂停，可修正各Agent输出后继续');
      }
    } catch {}
  };

  const handleResume = async () => {
    if (!taskId) return;
    setResuming(true);
    try {
      if (Object.keys(editingData).length > 0) {
        await fetch(apiBase() + '/tasks/' + taskId + '/edit-and-continue', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ edited_data: editingData }),
        });
      } else {
        await fetch(apiBase() + '/tasks/' + taskId + '/resume', { method: 'POST' });
      }
      setPaused(false);
      setPausedData(null);
      setEditingData({});
      // 重启SSE
      startSSE(taskId);
    } catch {} finally { setResuming(false); }
  };

  useEffect(() => {
    if (tab === 'chat') {
      setNewMsgCount(0);
      prevMsgCountRef.current = messages.length;
      setTimeout(scrollToBottom, 100);
    } else if (messages.length > prevMsgCountRef.current) {
      setNewMsgCount(prev => prev + (messages.length - prevMsgCountRef.current));
    }
  }, [tab, messages.length, scrollToBottom]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ========== 加载历史任务列表 ==========
  const loadTaskList = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await fetch(apiBase() + '/tasks/');
      if (res.ok) {
        const data = await res.json();
        setTaskList(data);
      }
    } catch (e) {
      console.error('Failed to load task list', e);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === 'history') {
      loadTaskList();
    }
  }, [tab, loadTaskList]);

  // ========== 加载任务详情 ==========
  const loadTaskDetail = useCallback(async (tid: string) => {
    setDetailLoading(true);
    setDetailTaskId(tid);
    setDetailMessages([]);
    setDetailResult(null);
    setActiveTab('messages');
    try {
      const [msgRes, resultRes] = await Promise.all([
        fetch(apiBase() + '/tasks/' + tid + '/messages'),
        fetch(apiBase() + '/tasks/' + tid + '/result'),
      ]);
      if (msgRes.ok) {
        const msgs = await msgRes.json();
        setDetailMessages(msgs.map((m: any) => ({
          id: m.id,
          sender: m.sender,
          sender_label: m.sender_label || TEAM_LABELS[m.sender] || m.sender,
          content: m.content,
          type: m.type || 'text',
          timestamp: m.timestamp,
        })));
      }
      if (resultRes.ok) {
        const r = await resultRes.json();
        setDetailResult(r);
      }
    } catch (e) {
      console.error('Failed to load task detail', e);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // ========== 任务提交 ==========
  const handleSubmit = async () => {
    if (!problemText.trim()) { alert('请输入问题描述'); return; }
    setSubmitting(true);
    try {
      const res = await fetch(apiBase() + '/tasks/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ problem_text: problemText, mode: solveMode }),
      });
      const data = await res.json();
      setTaskId(data.task_id);
      setTaskStatus('running');
      setProgress(0);
      setMessages([]);
      setTab('chat');
      addMsg('system', '系统', '任务已创建！ID: ' + data.task_id + '\n正在启动团队协作...', 'broadcast');
      startSSE(data.task_id);
    } catch (err) {
      console.error(err);
      alert('提交失败，请确认后端已启动');
    } finally {
      setSubmitting(false);
    }
  };

  // ========== SSE流 + 聊天室消息轮询 ==========
  const startSSE = (id: string) => {
    if (eventSource) eventSource.close();
    const es = new EventSource(apiBase() + '/tasks/' + id + '/stream');
    setEventSource(es);

    const msgPoll = setInterval(async () => {
      try {
        const res = await fetch(apiBase() + '/tasks/' + id + '/messages');
        if (res.ok) {
          const msgs: Message[] = await res.json();
          setMessages(msgs.map((m: any) => ({
            id: m.id,
            sender: m.sender,
            sender_label: m.sender_label || TEAM_LABELS[m.sender] || m.sender,
            content: m.content,
            type: m.type || 'text',
            timestamp: m.timestamp,
          })));
        }
      } catch {}
    }, 1000);

    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        setTaskStatus(d.status);
        setProgress(d.progress || 0);
        if (d.status === 'paused') { setPaused(true); es.close(); clearInterval(msgPoll); }
        if (d.status === 'completed' || d.status === 'failed') {
          es.close();
          clearInterval(msgPoll);
        }
      } catch {}
    };

    es.onerror = () => { es.close(); clearInterval(msgPoll); };
  };

  // ========== 文件上传 ==========
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList?.length) return;
    setUploading(true);
    for (const file of Array.from(fileList)) {
      const formData = new FormData();
      formData.append('file', file);
      if (taskId) formData.append('task_id', taskId);
      try {
        const res = await fetch(apiBase() + '/data/upload', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.success) {
          const info = data.shape ? '\n数据: ' + data.shape[0] + '行 x ' + data.shape[1] + '列' : '';
          addMsg('data_agent', '数据分析师', '文件已上传: ' + file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)' + info, 'result');
        }
      } catch {}
    }
    setUploading(false);
    loadFiles();
  };

  const loadFiles = async () => {
    try {
      const res = await fetch(apiBase() + '/data/files');
      if (res.ok) setFiles(await res.json());
    } catch {}
  };

  useEffect(() => { if (tab === 'files') loadFiles(); }, [tab]);

  const handleDeleteFile = async (fileName: string) => {
    if (!confirm(`确定删除文件 "${fileName}" 吗？`)) return;
    try {
      await fetch(apiBase() + '/data/files/' + encodeURIComponent(fileName), { method: 'DELETE' });
      loadFiles();
    } catch {}
  };

  // ========== 保存设置 ==========
  const handleSaveSettings = async () => {
    const input = document.getElementById('apiKeyInput') as HTMLInputElement;
    if (!input?.value.trim()) {
      const msg = document.getElementById('settingsMsg');
      if (msg) { msg.textContent = '请输入 API 密钥'; msg.style.color = '#e74c3c'; }
      return;
    }
    try {
      const res = await fetch(apiBase() + '/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minimax_api_key: input.value.trim() }),
      });
      const data = await res.json();
      const msg = document.getElementById('settingsMsg');
      if (msg) {
        msg.textContent = data.success ? '✓ API密钥保存成功！' : '保存失败';
        msg.style.color = data.success ? '#27ae60' : '#e74c3c';
      }
    } catch {
      const msg = document.getElementById('settingsMsg');
      if (msg) { msg.textContent = '保存失败，请检查后端连接'; msg.style.color = '#e74c3c'; }
    }
  };

  // ========== OCR ==========
  const handleOcrUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setOcrLoading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(apiBase() + '/data/upload', { method: 'POST', body: formData });
      const data = await res.json();
      const text = data.cleaned_text || data.raw_text || '';
      if (text) {
        setProblemText(prev => prev ? prev + '\n\n--- OCR识别内容 ---\n' + text : text);
        addMsg('coordinator', '协调者', 'OCR识别完成（已填入输入框）：\n' + text.slice(0, 300), 'result');
      } else {
        addMsg('system', '系统', '图片 ' + file.name + ' 上传成功，请手动输入题目描述', 'broadcast');
      }
    } catch {
      addMsg('system', '系统', '上传失败，请稍后重试', 'error');
    } finally {
      setOcrLoading(false);
    }
  };

  // ========== 删除历史任务 ==========
  const handleDeleteTask = async (tid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`确定删除任务 "${tid}" 吗？`)) return;
    try {
      await fetch(apiBase() + '/tasks/' + tid, { method: 'DELETE' });
      loadTaskList();
    } catch {}
  };

  // ========== 工具 ==========
  const addMsg = (sender: string, label: string, content: string, type: string) => {
    setMessages(prev => [...prev, {
      id: 'msg_' + Date.now() + '_' + Math.random().toString(36).slice(2),
      sender,
      sender_label: label,
      content,
      type,
      timestamp: new Date().toISOString(),
    }]);
  };

  // 编辑暂停数据的JSON内容
  const handleEditChange = (key: string, value: string) => {
    try { setEditingData((prev: Record<string,any>) => ({ ...prev, [key]: JSON.parse(value) })); }
    catch { setEditingData((prev: Record<string,any>) => ({ ...prev, [key]: value })); }
  };

  // ========== 渲染消息 ==========
  const renderMsg = (msg: Message, ref?: React.RefObject<HTMLDivElement>) => (
    <div
      key={msg.id}
      ref={ref}
      className={msg.type === 'result' ? styles.msgResult : styles.msg}
      style={{ borderLeftColor: TEAM_COLORS[msg.sender] || '#666' }}
    >
      <div className={styles.msgHeader}>
        <span style={{ color: TEAM_COLORS[msg.sender] || '#666' }}>{msg.sender_label}</span>
        {msg.type === 'result' && <span className={styles.resultBadge}>📋 详细结果</span>}
        <span className={styles.msgTime}>{formatTime(msg.timestamp)}</span>
      </div>
      <div className={msg.type === 'result' ? styles.msgContentResult : styles.msgContent}>
        {msg.content.split('\n').map((line, i) => {
          if (line.startsWith('```')) return null;
          if (line.startsWith('- ')) return <div key={i} className={styles.listItem}>{line.slice(2)}</div>;
          if (line.startsWith('**') && line.endsWith('**')) return <div key={i} className={styles.boldLine}>{line.slice(2, -2)}</div>;
          return <div key={i}>{line || '\u00A0'}</div>;
        })}
      </div>
    </div>
  );

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <span className={styles.headerTitle}>数学建模论文自动生成系统</span>
        <p className={styles.subtitle}>Multi-Agent团队协作 · 实时讨论 · 任务历史</p>
      </header>

      <div className={styles.tabs}>
        {(['input', 'chat', 'files', 'history', 'settings'] as const).map(t => (
          <button
            key={t}
            className={tab === t ? styles.tab + ' ' + styles.active : styles.tab}
            onClick={() => { setTab(t); if (t !== 'history') setDetailTaskId(null); }}
          >
            {t === 'input' && '📥 输入'}
            {t === 'chat' && '💬 讨论' + (messages.length > 0 ? `(${messages.length})` : '')}
            {t === 'files' && '📁 数据'}
            {t === 'history' && '📋 历史' + (taskList.length > 0 ? `(${taskList.length})` : '')}
            {t === 'settings' && '⚙️ 设置'}
          </button>
        ))}
      </div>

      <div className={styles.container}>
        {/* ===== 输入标签 ===== */}
        {tab === 'input' && (
          <div className={styles.card}>
            <span className={styles.cardTitle}>输入数学建模问题</span>

            <div className={styles.ocrRow}>
              <label className={styles.ocrBtn}>
                {ocrLoading ? '识别中...' : '📷 上传题目图片(OCR)'}
                <input type="file" accept="image/*,.pdf" onChange={handleOcrUpload} style={{ display: 'none' }} disabled={ocrLoading} />
              </label>
              <span className={styles.ocrHint}>支持 JPG/PNG/PDF，自动识别题目</span>
            </div>

            <textarea
              className={styles.textarea}
              placeholder={'请描述数学建模问题，包括：\n1. 问题背景\n2. 具体要求（预测/优化/评价等）\n3. 约束条件\n4. 如有数据文件，请先到「数据」标签上传'}
              value={problemText}
              onChange={e => setProblemText(e.target.value)}
              rows={12}
            />

            <div className={styles.modeSelector}>
              <span className={styles.modeLabel}>求解模式：</span>
              <label className={`${styles.modeOption} ${solveMode === 'sequential' ? styles.modeSelected : ''}`}>
                <input type="radio" name="solveMode" value="sequential" checked={solveMode === 'sequential'} onChange={() => setSolveMode('sequential')} />
                <span>逐个递进</span>
                <span className={styles.modeHint}>前序结果递进至后序</span>
              </label>
              <label className={`${styles.modeOption} ${solveMode === 'batch' ? styles.modeSelected : ''}`}>
                <input type="radio" name="solveMode" value="batch" checked={solveMode === 'batch'} onChange={() => setSolveMode('batch')} />
                <span>批量并行</span>
                <span className={styles.modeHint}>各子问题独立求解</span>
              </label>
            </div>

            {taskStatus === 'running' && (
              <div className={styles.progressBar}>
                <div className={styles.progressFill} style={{ width: progress + '%' }} />
                <span className={styles.progressText}>{progress}%</span>
              </div>
            )}

            <div className={styles.btnRow}>
              <button className={styles.submitBtn} onClick={handleSubmit} disabled={submitting || !problemText.trim()}>
                {submitting ? '🚀 启动中...' : taskStatus === 'running' ? `🔄 进行中 ${progress}%` : '🚀 启动团队协作'}
              </button>
              {taskId && (
                <button className={styles.secondaryBtn} onClick={() => setTab('chat')}>💬 查看讨论</button>
              )}
            </div>

            {taskId && (
              <div className={styles.taskInfo}>
                <span>任务ID: {taskId}</span>
                <span>状态: <StatusBadge status={taskStatus} /></span>
                <span>进度: {progress}%</span>
              </div>
            )}
          </div>
        )}

        {/* ===== 讨论标签 ===== */}
        {tab === 'chat' && (
          <div className={styles.card}>
            <div className={styles.chatHeader}>
              <span className={styles.chatHeaderTitle}>💬 Agent团队实时讨论</span>
              <div className={styles.teamBadges}>
                {Object.entries(TEAM_LABELS).filter(([k]) => k !== 'system').map(([k, v]) => (
                  <span key={k} className={styles.badge} style={{ background: TEAM_COLORS[k] }}>{v}</span>
                ))}
              </div>
              {taskId && taskStatus === 'running' && (
                <button className={styles.pauseBtn} onClick={handlePause}>⏸ 暂停</button>
              )}
              {paused && (
                <button className={styles.resumeBtn} onClick={handleResume} disabled={resuming}>
                  {resuming ? '继续中...' : '▶ 继续执行'}
                </button>
              )}
            </div>

            {/* 暂停编辑面板 */}
            {paused && pausedData && (
              <div className={styles.pauseEditor}>
                <div className={styles.pauseEditorTitle}>⚠️ 任务已暂停 - 可修正以下内容后继续</div>
                <div className={styles.pauseEditorHint}>在下方JSON编辑器中修正内容，完成后点击「继续执行」</div>
                {Object.entries(pausedData).map(([key, value]) => {
                  const agentName = { analyzer_agent: '分析师', data_agent: '数据分析师', research_agent: '研究员', modeler_agent: '建模师', section_results: '模型/章节' }[key] || key;
                  return (
                    <div key={key} className={styles.pauseEditSection}>
                      <div className={styles.pauseEditLabel}>{agentName}</div>
                      <textarea
                        className={styles.pauseEditTextarea}
                        defaultValue={JSON.stringify(value, null, 2)}
                        onChange={e => handleEditChange(key, e.target.value)}
                        rows={6}
                      />
                    </div>
                  );
                })}
              </div>
            )}

            <div className={styles.messages}>
              {messages.length === 0 && (
                <div className={styles.emptyState}>提交问题后，各Agent将在此展开讨论</div>
              )}
              {messages.map(msg => renderMsg(msg))}
              <div ref={messagesEndRef} />
            </div>
          </div>
        )}

        {/* ===== 历史任务标签 ===== */}
        {tab === 'history' && (
          <div className={styles.historyLayout}>
            {/* 左侧：任务列表 */}
            <div className={styles.historyListPanel}>
              <div className={styles.historyListHeader}>
                <span className={styles.cardTitle}>📋 历史任务</span>
                <div className={styles.historyHeaderBtns}>
                  {selectedTaskIds.size > 0 && (
                    <button className={styles.batchDeleteBtn} onClick={handleBatchDelete} disabled={batchDeleting}>
                      🗑️ 批量删除({selectedTaskIds.size})
                    </button>
                  )}
                  <button className={styles.refreshBtn} onClick={loadTaskList} disabled={historyLoading}>
                    {historyLoading ? '加载中...' : '🔄 刷新'}
                  </button>
                </div>
              </div>

              {historyLoading && taskList.length === 0 && (
                <div className={styles.emptyState}>加载中...</div>
              )}

              {!historyLoading && taskList.length === 0 && (
                <div className={styles.emptyState}>暂无历史任务<br/>提交新任务后会在此显示</div>
              )}

              {taskList.map(task => (
                <div
                  key={task.task_id}
                  className={`${styles.historyItem} ${detailTaskId === task.task_id ? styles.historyItemActive : ''}`}
                  onClick={() => loadTaskDetail(task.task_id)}
                >
                  <div className={styles.historyItemCheck}>
                    <input type="checkbox" checked={selectedTaskIds.has(task.task_id)} onChange={() => toggleTaskSelection(task.task_id)} onClick={e => e.stopPropagation()} />
                  </div>
                  <div className={styles.historyItemTop}>
                    <StatusBadge status={task.status} />
                    <span className={styles.historyItemTime}>{formatTime(task.created_at)}</span>
                  </div>
                  <div className={styles.historyItemPreview}>
                    {task.problem_preview || '（无题目描述）'}
                  </div>
                  <div className={styles.historyItemMeta}>
                    {task.current_step && <span>📍 {task.current_step}</span>}
                    {task.total_steps > 0 && <span>📊 {task.total_steps}步骤</span>}
                    <button
                      className={styles.historyDeleteBtn}
                      onClick={(e) => handleDeleteTask(task.task_id, e)}
                      title="删除任务"
                    >
                      🗑️
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* 右侧：任务详情 */}
            <div className={styles.historyDetailPanel}>
              {!detailTaskId && (
                <div className={styles.emptyState}>👈 点击左侧任务查看详情</div>
              )}

              {detailLoading && (
                <div className={styles.emptyState}>加载中...</div>
              )}

              {detailTaskId && !detailLoading && (
                <>
                  <div className={styles.detailHeader}>
                    <span className={styles.cardTitle}>📄 任务详情: {detailTaskId}</span>
                    <button className={styles.exportBtn} onClick={() => handleExport(detailTaskId!)} disabled={exporting}>
                      {exporting ? '导出中...' : '💾 导出到桌面'}
                    </button>
                    <div className={styles.detailTabs}>
                      {(['messages', 'result', 'info'] as const).map(t => (
                        <button
                          key={t}
                          className={activeTab === t ? styles.detailTabActive : styles.detailTab}
                          onClick={() => setActiveTab(t)}
                        >
                          {t === 'messages' && '💬 讨论记录'}
                          {t === 'result' && '📊 结果'}
                          {t === 'info' && 'ℹ️ 详情'}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* 讨论记录 */}
                  {activeTab === 'messages' && (
                    <div className={styles.detailMessages}>
                      {detailMessages.length === 0 && <div className={styles.emptyState}>暂无讨论记录</div>}
                      {detailMessages.map(msg => renderMsg(msg))}
                    </div>
                  )}

                  {/* 结果 */}
                  {activeTab === 'result' && (
                    <div className={styles.resultPanel}>
                      {detailResult?.output?.latex_code ? (
                        <div className={styles.resultSection}>
                          <div className={styles.resultSectionTitle}>📝 LaTeX论文代码</div>
                          <textarea
                            className={styles.codeTextarea}
                            defaultValue={detailResult.output.latex_code}
                            readOnly
                          />
                          <div className={styles.resultSectionTitle}>📄 摘要</div>
                          <p>{detailResult.output.abstract || '暂无摘要'}</p>
                          <div className={styles.resultSectionTitle}>🏷️ 关键词</div>
                          <p>{(detailResult.output.keywords || []).join(' · ')}</p>
                          {detailResult.output.analyses && detailResult.output.analyses.length > 0 && (
                            <>
                              <div className={styles.resultSectionTitle}>📊 数据分析</div>
                              {detailResult.output.analyses.map((a: any, i: number) => (
                                <div key={i} className={styles.analysisCard}>
                                  <strong>{a.file_name}</strong>
                                  <span> {a.shape?.[0]}行 × {a.shape?.[1]}列</span>
                                  <div>{a.data_quality?.missing_rate === 0 ? '✓ 无缺失值' : `⚠ 缺失率 ${a.data_quality?.missing_rate}`}</div>
                                  {(a.insights || []).map((ins: string, j: number) => (
                                    <div key={j} className={styles.listItem}>• {ins}</div>
                                  ))}
                                </div>
                              ))}
                            </>
                          )}
                        </div>
                      ) : (
                        <div className={styles.emptyState}>
                          {detailResult ? '该任务暂无完整结果' : '无法加载结果，请检查后端'}
                        </div>
                      )}
                      {detailResult?.completed_at && (
                        <div className={styles.completedAt}>✅ 完成时间: {formatTime(detailResult.completed_at)}</div>
                      )}
                    </div>
                  )}

                  {/* 详情 */}
                  {activeTab === 'info' && (
                    <div className={styles.infoPanel}>
                      {taskList.find(t => t.task_id === detailTaskId) && (() => {
                        const t = taskList.find(t => t.task_id === detailTaskId)!;
                        return (
                          <>
                            <div className={styles.infoRow}>
                              <span className={styles.infoLabel}>任务ID</span>
                              <code className={styles.infoValue}>{t.task_id}</code>
                            </div>
                            <div className={styles.infoRow}>
                              <span className={styles.infoLabel}>状态</span>
                              <StatusBadge status={t.status} />
                            </div>
                            <div className={styles.infoRow}>
                              <span className={styles.infoLabel}>创建时间</span>
                              <span className={styles.infoValue}>{formatTime(t.created_at)}</span>
                            </div>
                            {t.completed_at && (
                              <div className={styles.infoRow}>
                                <span className={styles.infoLabel}>完成时间</span>
                                <span className={styles.infoValue}>{formatTime(t.completed_at)}</span>
                              </div>
                            )}
                            <div className={styles.infoRow}>
                              <span className={styles.infoLabel}>当前步骤</span>
                              <span className={styles.infoValue}>{t.current_step || '无'}</span>
                            </div>
                            {t.error && (
                              <div className={styles.infoRow}>
                                <span className={styles.infoLabel}>错误信息</span>
                                <span className={styles.infoError}>{t.error}</span>
                              </div>
                            )}
                            <div className={styles.infoRow}>
                              <span className={styles.infoLabel}>题目预览</span>
                              <span className={styles.infoValue}>{t.problem_preview || '无'}</span>
                            </div>
                          </>
                        );
                      })()}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        {/* ===== 文件标签 ===== */}
        {tab === 'files' && (
          <div className={styles.card}>
            <span className={styles.cardTitle}>📁 数据文件管理</span>
            <div className={styles.uploadRow}>
              <label className={styles.uploadBtn}>
                {uploading ? '上传中...' : '📤 上传数据文件'}
                <input type="file" accept=".csv,.xlsx,.xls,.json,.txt,.tsv,.parquet" multiple onChange={handleFileUpload} style={{ display: 'none' }} disabled={uploading} />
              </label>
              <span className={styles.hint}>支持 CSV · Excel · JSON · TXT · TSV</span>
            </div>

            <div>
              {files.length === 0 && <p className={styles.emptyState}>暂无文件，请上传数据文件</p>}
              {files.map((f, i) => (
                <div key={i} className={styles.fileItem}>
                  <span className={styles.fileIcon}>{f.type}</span>
                  <div className={styles.fileInfo}>
                    <span className={styles.fileName}>{f.name}</span>
                    <span className={styles.fileSize}>
                      {(f.size / 1024).toFixed(1)} KB
                      {f.shape ? ' · ' + f.shape[0] + '行 x ' + f.shape[1] + '列' : ''}
                    </span>
                  </div>
                  {f.insights && f.insights.length > 0 && (
                    <div className={styles.insights}>
                      {f.insights.slice(0, 2).map((ins, j) => (
                        <span key={j} className={styles.insightTag}>{ins}</span>
                      ))}
                    </div>
                  )}
                  <button className={styles.deleteBtn} onClick={() => handleDeleteFile(f.name)} title="删除">✕</button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ===== 设置标签 ===== */}
        {tab === 'settings' && (
          <div className={styles.card}>
            <span className={styles.cardTitle}>⚙️ 系统设置</span>

            <div className={styles.settingsSection}>
              <div className={styles.settingsLabel}>MiniMax API 密钥</div>
              <div className={styles.apiKeyRow}>
                <input
                  type="password"
                  className={styles.apiKeyInput}
                  placeholder="输入 MiniMax API 密钥（必填）"
                  defaultValue=""
                  id="apiKeyInput"
                />
              </div>
              <div className={styles.apiKeyHint}>
                请在 <a href="https://platform.minimax.chat" target="_blank" rel="noopener" style={{ color: '#3498db' }}>MiniMax开放平台</a> 获取密钥
              </div>
              <div className={styles.btnRow}>
                <button className={styles.submitBtn} onClick={handleSaveSettings}>💾 保存设置</button>
              </div>
              <div id="settingsMsg" />
            </div>

            <div className={styles.divider} />

            <div className={styles.noteBox}>
              <strong>📍 访问地址：</strong>
              <code>本机: http://localhost:3000</code><br/>
              <code>局域网: http://100.94.99.122:3000</code><br/>
              <strong>📖 后端API文档：</strong><code>http://localhost:8000/docs</code>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
