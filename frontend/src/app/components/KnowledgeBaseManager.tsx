'use client';

import { useState, useEffect, useCallback } from 'react';

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

interface KBDoc {
  id: string;
  title: string;
  source?: string;
  content_length: number;
  metadata?: Record<string, any>;
}

interface QueryResult {
  id: string;
  title: string;
  content: string;
  source?: string;
  score: number;
}

export default function KnowledgeBaseManager() {
  const [docs, setDocs] = useState<KBDoc[]>([]);
  const [stats, setStats] = useState<{ total_documents: number; total_chunks: number; sources: string[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');

  // Add doc form
  const [showAdd, setShowAdd] = useState(false);
  const [docForm, setDocForm] = useState({ title: '', content: '', source: '' });
  const [adding, setAdding] = useState(false);

  // File upload
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<string | null>(null);

  // Query
  const [showQuery, setShowQuery] = useState(false);
  const [queryText, setQueryText] = useState('');
  const [queryResults, setQueryResults] = useState<QueryResult[]>([]);
  const [querying, setQuerying] = useState(false);

  // Context query (for agent prompt preview)
  const [showContext, setShowContext] = useState(false);
  const [contextText, setContextText] = useState('');
  const [contextResult, setContextResult] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [docsRes, statsRes] = await Promise.all([
        fetch(apiBase() + '/knowledge/'),
        fetch(apiBase() + '/knowledge/stats'),
      ]);
      if (docsRes.ok) {
        const data = await docsRes.json();
        setDocs(data.documents || []);
      }
      if (statsRes.ok) {
        setStats(await statsRes.json());
      }
    } catch {} finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAddDoc = async () => {
    if (!docForm.title.trim() || !docForm.content.trim()) { setMsg('标题和内容不能为空'); return; }
    setAdding(true);
    try {
      const res = await fetch(apiBase() + '/knowledge/documents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: docForm.title.trim(),
          content: docForm.content.trim(),
          source: docForm.source.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setMsg(`文档 "${docForm.title}" 已添加`);
        setShowAdd(false);
        setDocForm({ title: '', content: '', source: '' });
        load();
      } else {
        setMsg(data.detail || '添加失败');
      }
    } catch { setMsg('添加失败'); } finally { setAdding(false); }
  };

  const handleDeleteDoc = async (docId: string) => {
    try {
      const res = await fetch(apiBase() + '/knowledge/documents/' + docId, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) { setMsg('文档已删除'); load(); }
      else { setMsg(data.detail || '删除失败'); }
    } catch { setMsg('删除失败'); }
  };

  const handleQuery = async () => {
    if (!queryText.trim()) return;
    setQuerying(true);
    try {
      const res = await fetch(apiBase() + '/knowledge/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: queryText.trim(), top_k: 5 }),
      });
      const data = await res.json();
      setQueryResults(data.results || []);
    } catch { setQueryResults([]); } finally { setQuerying(false); }
  };

  const handleQueryContext = async () => {
    if (!contextText.trim()) return;
    setQuerying(true);
    try {
      const res = await fetch(apiBase() + '/knowledge/query/context', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: contextText.trim(), top_k: 3, max_chars: 2000 }),
      });
      const data = await res.json();
      setContextResult(data.context || '(无相关上下文)');
    } catch { setContextResult('查询失败'); } finally { setQuerying(false); }
  };

  const handleSave = async () => {
    try {
      const res = await fetch(apiBase() + '/knowledge/save', { method: 'POST' });
      const data = await res.json();
      if (data.success) setMsg('知识库已保存到磁盘');
      else setMsg('保存失败');
    } catch { setMsg('保存失败'); }
  };

  const handleLoad = async () => {
    try {
      const res = await fetch(apiBase() + '/knowledge/load', { method: 'POST' });
      const data = await res.json();
      if (data.success) { setMsg(`已加载 ${data.documents} 个文档`); load(); }
      else setMsg('加载失败');
    } catch { setMsg('加载失败'); }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length) return;
    setUploading(true);
    setUploadResult(null);
    for (const file of Array.from(files)) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await fetch(apiBase() + '/knowledge/upload?chunk_size=500&overlap=50', {
          method: 'POST',
          body: formData,
        });
        const data = await res.json();
        if (data.success) {
          setUploadResult(`✓ ${data.filename}: ${data.chunks} 个分块, ${data.total_chars} 字符`);
          load();
        } else {
          setUploadResult(`✗ ${file.name}: ${data.detail || '上传失败'}`);
        }
      } catch {
        setUploadResult(`✗ ${file.name}: 上传失败`);
      }
    }
    setUploading(false);
    // Reset file input
    e.target.value = '';
  };

  if (loading) return <div style={{ color: '#aaa', textAlign: 'center', padding: '2rem' }}>加载中...</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ fontSize: '1.1rem', color: '#fff', fontWeight: 600 }}>📚 知识库</span>
            <div style={{ color: '#888', fontSize: '0.8rem', marginTop: '0.3rem' }}>
              RAG 知识增强：添加数学建模相关知识，Agent 会自动检索并注入上下文
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button onClick={handleSave} style={{ padding: '0.4rem 0.8rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 6, color: '#3498db', fontSize: '0.78rem', cursor: 'pointer' }}>💾 保存</button>
            <button onClick={handleLoad} style={{ padding: '0.4rem 0.8rem', background: 'rgba(241,196,15,0.15)', border: '1px solid rgba(241,196,15,0.3)', borderRadius: 6, color: '#f1c40f', fontSize: '0.78rem', cursor: 'pointer' }}>📂 加载</button>
            <button onClick={() => setShowQuery(!showQuery)} style={{ padding: '0.4rem 0.8rem', background: 'rgba(155,89,182,0.15)', border: '1px solid rgba(155,89,182,0.3)', borderRadius: 6, color: '#9b59b6', fontSize: '0.78rem', cursor: 'pointer' }}>🔍 查询</button>
            <label style={{ padding: '0.4rem 0.8rem', background: 'rgba(46,204,113,0.15)', border: '1px solid rgba(46,204,113,0.3)', borderRadius: 6, color: '#2ecc71', fontSize: '0.78rem', cursor: uploading ? 'not-allowed' : 'pointer' }}>
              {uploading ? '上传中...' : '📤 上传文件'}
              <input type="file" accept=".md,.txt,.markdown,.rst,.tex,.json,.csv" multiple onChange={handleFileUpload} style={{ display: 'none' }} disabled={uploading} />
            </label>
            <button onClick={() => setShowAdd(!showAdd)} style={{ padding: '0.4rem 0.8rem', background: 'rgba(243,156,18,0.15)', border: '1px solid rgba(243,156,18,0.3)', borderRadius: 6, color: '#f39c12', fontSize: '0.78rem', cursor: 'pointer' }}>+ 手动添加</button>
          </div>
        </div>
      </div>

      {/* Upload result */}
      {uploadResult && (
        <div style={{ padding: '0.5rem 1rem', background: uploadResult.startsWith('✓') ? 'rgba(46,204,113,0.1)' : 'rgba(231,76,60,0.1)', borderRadius: 8, fontSize: '0.85rem', color: uploadResult.startsWith('✓') ? '#2ecc71' : '#e74c3c' }}>
          {uploadResult}
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div style={{ display: 'flex', gap: '1rem', padding: '0.8rem 1.5rem', background: 'rgba(0,0,0,0.2)', borderRadius: 14 }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ color: '#fff', fontSize: '1.5rem', fontWeight: 700 }}>{stats.total_documents}</div>
            <div style={{ color: '#888', fontSize: '0.75rem' }}>文档数</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ color: '#fff', fontSize: '1.5rem', fontWeight: 700 }}>{stats.total_chunks}</div>
            <div style={{ color: '#888', fontSize: '0.75rem' }}>分块数</div>
          </div>
          <div style={{ textAlign: 'center', flex: 1 }}>
            <div style={{ color: '#888', fontSize: '0.75rem', marginBottom: '0.3rem' }}>来源</div>
            <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap', justifyContent: 'center' }}>
              {(stats.sources.length > 0 ? stats.sources : ['(无)']).map(s => (
                <span key={s} style={{ padding: '0.15rem 0.4rem', background: 'rgba(255,255,255,0.08)', borderRadius: 4, color: '#aaa', fontSize: '0.7rem' }}>{s}</span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Add document */}
      {showAdd && (
        <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
          <span style={{ fontSize: '1rem', color: '#fff', fontWeight: 600, display: 'block', marginBottom: '1rem' }}>添加文档</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
            <input
              value={docForm.title}
              onChange={e => setDocForm(f => ({ ...f, title: e.target.value }))}
              placeholder="标题（如：线性规划基础）"
              style={{ padding: '0.75rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }}
            />
            <textarea
              value={docForm.content}
              onChange={e => setDocForm(f => ({ ...f, content: e.target.value }))}
              placeholder="内容（数学建模知识点、算法说明等）"
              rows={6}
              style={{ padding: '0.75rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem', resize: 'vertical', fontFamily: 'inherit' }}
            />
            <input
              value={docForm.source}
              onChange={e => setDocForm(f => ({ ...f, source: e.target.value }))}
              placeholder="来源（可选，如：教材、论文、经验）"
              style={{ padding: '0.75rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }}
            />
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
            <button onClick={handleAddDoc} disabled={adding} style={{ padding: '0.6rem 1.5rem', background: 'linear-gradient(135deg, #2ecc71, #27ae60)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>
              {adding ? '添加中...' : '确认添加'}
            </button>
            <button onClick={() => { setShowAdd(false); setDocForm({ title: '', content: '', source: '' }); }} style={{ padding: '0.6rem 1.5rem', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#aaa', cursor: 'pointer' }}>
              取消
            </button>
          </div>
        </div>
      )}

      {/* Query */}
      {showQuery && (
        <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
          <span style={{ fontSize: '1rem', color: '#fff', fontWeight: 600, display: 'block', marginBottom: '1rem' }}>🔍 查询知识库</span>
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            <input
              value={queryText}
              onChange={e => setQueryText(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleQuery()}
              placeholder="输入问题..."
              style={{ flex: 1, padding: '0.75rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }}
            />
            <button onClick={handleQuery} disabled={querying} style={{ padding: '0.75rem 1.5rem', background: 'rgba(155,89,182,0.2)', border: '1px solid rgba(155,89,182,0.3)', borderRadius: 8, color: '#9b59b6', cursor: 'pointer', fontWeight: 600 }}>
              {querying ? '查询中...' : '查询'}
            </button>
          </div>

          {/* Context preview */}
          <details style={{ marginBottom: '1rem' }}>
            <summary style={{ color: '#ddd', cursor: 'pointer', fontSize: '0.85rem' }}>Agent 注入预览（格式化上下文）</summary>
            <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
              <input
                value={contextText}
                onChange={e => setContextText(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleQueryContext()}
                placeholder="输入问题预览 Agent 会看到的上下文..."
                style={{ flex: 1, padding: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, color: '#e0e0e0', fontSize: '0.85rem' }}
              />
              <button onClick={handleQueryContext} disabled={querying} style={{ padding: '0.5rem 1rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 6, color: '#3498db', cursor: 'pointer', fontSize: '0.8rem' }}>
                {querying ? '查询中...' : '预览'}
              </button>
            </div>
            {contextResult && (
              <pre style={{ marginTop: '0.5rem', padding: '0.8rem', background: 'rgba(0,0,0,0.3)', borderRadius: 8, color: '#ccc', fontSize: '0.8rem', whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto', border: '1px solid rgba(255,255,255,0.1)' }}>
                {contextResult}
              </pre>
            )}
          </details>

          {/* Results */}
          {queryResults.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {queryResults.map(r => (
                <div key={r.id} style={{ padding: '0.8rem', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.3rem' }}>
                    <span style={{ color: '#fff', fontWeight: 600 }}>{r.title}</span>
                    <span style={{ color: '#3498db', fontSize: '0.8rem' }}>相关度: {(r.score * 100).toFixed(1)}%</span>
                  </div>
                  <div style={{ color: '#aaa', fontSize: '0.85rem', whiteSpace: 'pre-wrap' }}>{r.content.slice(0, 300)}{r.content.length > 300 ? '...' : ''}</div>
                  {r.source && <div style={{ color: '#666', fontSize: '0.75rem', marginTop: '0.3rem' }}>来源: {r.source}</div>}
                </div>
              ))}
            </div>
          )}
          {showQuery && queryResults.length === 0 && !querying && (
            <div style={{ color: '#666', textAlign: 'center', padding: '1rem' }}>输入问题后查询</div>
          )}
        </div>
      )}

      {/* Document list */}
      <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
        <span style={{ fontSize: '1.1rem', color: '#fff', fontWeight: 600, display: 'block', marginBottom: '1rem' }}>📄 文档列表</span>
        {docs.length === 0 && (
          <div style={{ color: '#666', textAlign: 'center', padding: '2rem' }}>
            暂无文档，请点击「添加文档」
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {docs.map(doc => (
            <div key={doc.id} style={{ display: 'flex', alignItems: 'center', gap: '0.8rem', padding: '0.8rem', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8 }}>
              <span style={{ color: '#fff', fontWeight: 600, flex: 1 }}>{doc.title}</span>
              <span style={{ color: '#888', fontSize: '0.8rem' }}>{(doc.content_length || 0)} 字符</span>
              {doc.source && (
                <span style={{ padding: '0.15rem 0.4rem', background: 'rgba(52,152,219,0.1)', border: '1px solid rgba(52,152,219,0.2)', borderRadius: 4, color: '#3498db', fontSize: '0.7rem' }}>{doc.source}</span>
              )}
              <button onClick={() => handleDeleteDoc(doc.id)} style={{ padding: '0.2rem 0.5rem', background: 'rgba(231,76,60,0.15)', border: '1px solid rgba(231,76,60,0.3)', borderRadius: 4, color: '#e74c3c', fontSize: '0.7rem', cursor: 'pointer' }}>🗑️</button>
            </div>
          ))}
        </div>
      </div>

      {msg && <div style={{ fontSize: '0.85rem', color: msg.includes('失败') ? '#e74c3c' : '#2ecc71', textAlign: 'center' }}>{msg}</div>}
    </div>
  );
}
