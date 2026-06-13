'use client';

import { useEffect, useRef, useState } from 'react';
import styles from './PdfManager.module.css';

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

interface PdfFile {
  file_id: string;
  filename: string;
  size: number;
  pages?: number;
  source: string;
  url?: string;
  uploaded_at: number;
  parsed?: boolean;
}

interface ParseResult {
  file_id: string;
  filename: string;
  strategy: string;
  pages: number;
  text: string;
  markdown?: string;
  metadata?: Record<string, any>;
  errors?: string[];
}

export default function PdfManager() {
  const [files, setFiles] = useState<PdfFile[]>([]);
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [parsing, setParsing] = useState<string | null>(null);
  const [result, setResult] = useState<ParseResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [strategy, setStrategy] = useState('auto');
  const [useVision, setUseVision] = useState(false);
  const [visionProvider, setVisionProvider] = useState('');
  const [providers, setProviders] = useState<{ id: string; name: string; model?: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadFiles();
    loadProviders();
  }, []);

  const loadFiles = async () => {
    try {
      const res = await fetch(apiBase() + '/pdf/files');
      if (res.ok) {
        const data = await res.json();
        setFiles(data.files || []);
      }
    } catch (e) {
      console.error('加载 PDF 列表失败', e);
    }
  };

  const loadProviders = async () => {
    try {
      const res = await fetch(apiBase() + '/info');
      if (res.ok) {
        const data = await res.json();
        const ps = (data.providers || [])
          .filter((p: any) => p.available)
          .map((p: any) => ({ id: p.id, name: p.name, model: p.model }));
        setProviders(ps);
        if (ps.length > 0 && !visionProvider) {
          setVisionProvider(ps[0].id);
        }
      }
    } catch (e) {
      console.error('加载 Provider 失败', e);
    }
  };

  const formatSize = (size: number) => {
    if (size < 1024) return size + ' B';
    if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB';
    return (size / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(apiBase() + '/pdf/upload', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '上传失败');
      await loadFiles();
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(apiBase() + '/pdf/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '下载失败');
      setUrl('');
      await loadFiles();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleParse = async (fileId: string) => {
    setParsing(fileId);
    setError(null);
    setResult(null);
    try {
      const body: any = {
        file_id: fileId,
        strategy,
        use_vision: useVision,
      };
      if (useVision && visionProvider) {
        body.vision_provider = visionProvider;
        body.vision_max_pages = 3;
      }
      const res = await fetch(apiBase() + '/pdf/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '解析失败');
      setResult(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setParsing(null);
    }
  };

  const handleDelete = async (fileId: string) => {
    if (!confirm('确定删除该 PDF？')) return;
    try {
      const res = await fetch(apiBase() + '/pdf/files/' + fileId, { method: 'DELETE' });
      if (res.ok) {
        setFiles(files.filter((f) => f.file_id !== fileId));
        if (result?.file_id === fileId) setResult(null);
      }
    } catch (e) {
      console.error('删除失败', e);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.title}>📄 PDF 解析中心</div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>上传 / 下载 PDF</div>
        <div className={styles.row}>
          <input
            type="file"
            accept=".pdf"
            ref={fileInputRef}
            className={styles.fileInput}
            id="pdf-upload"
            onChange={handleFileChange}
          />
          <label htmlFor="pdf-upload" className={styles.fileLabel}>
            {loading ? '处理中...' : '📤 选择 PDF 上传'}
          </label>
          <input
            type="text"
            className={styles.input}
            placeholder="输入 PDF 链接或 arXiv 摘要页 URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button className={styles.btn} onClick={handleDownload} disabled={loading || !url.trim()}>
            ⬇️ 下载
          </button>
        </div>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>解析策略</div>
        <div className={styles.row}>
          <select className={styles.select} value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            <option value="auto">自动选择</option>
            <option value="pymupdf4llm">PyMuPDF4LLM（本地保底）</option>
            <option value="vision">多模态视觉（限速）</option>
          </select>
          <label className={styles.checkbox}>
            <input
              type="checkbox"
              checked={useVision}
              onChange={(e) => setUseVision(e.target.checked)}
            />
            启用视觉辅助
          </label>
          {useVision && (
            <select
              className={styles.select}
              value={visionProvider}
              onChange={(e) => setVisionProvider(e.target.value)}
            >
              <option value="">选择 Provider</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} {p.model ? `(${p.model})` : ''}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      <div className={styles.section}>
        <div className={styles.sectionTitle}>已下载 PDF</div>
        {files.length === 0 ? (
          <div className={styles.empty}>暂无 PDF 文件</div>
        ) : (
          <div className={styles.fileList}>
            {files.map((f) => (
              <div key={f.file_id} className={styles.fileCard}>
                <div className={styles.fileInfo}>
                  <span className={styles.fileName}>{f.filename}</span>
                  <span className={styles.fileMeta}>
                    {formatSize(f.size)} · {f.pages ?? '?'} 页 · {f.source}
                  </span>
                </div>
                <div className={styles.fileActions}>
                  <button
                    className={styles.btn}
                    onClick={() => handleParse(f.file_id)}
                    disabled={parsing === f.file_id}
                  >
                    {parsing === f.file_id ? '解析中...' : '🔍 解析'}
                  </button>
                  <button className={styles.btnSecondary} onClick={() => handleDelete(f.file_id)}>
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {result && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>解析结果</div>
          <div className={styles.result}>
            <div className={styles.resultMeta}>
              <span className={styles.tag}>策略: {result.strategy}</span>
              <span className={styles.tag}>页数: {result.pages}</span>
              {result.metadata?.total_pages && (
                <span className={styles.tag}>总页数: {result.metadata.total_pages}</span>
              )}
            </div>
            <pre className={styles.resultText}>{result.markdown || result.text}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
