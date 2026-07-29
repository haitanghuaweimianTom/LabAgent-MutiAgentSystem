'use client';

import { useEffect, useRef, useState } from 'react';
import { apiBase } from '@/lib/api';

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
    <div className="bg-card border border-border rounded-xl p-5 flex flex-col gap-4">
      <div className="text-base text-foreground font-semibold">📄 PDF 解析中心</div>

      <div className="flex flex-col gap-2.5">
        <div className="text-sm text-muted-foreground font-semibold">上传 / 下载 PDF</div>
        <div className="flex gap-2 items-center flex-wrap">
          <input
            type="file"
            accept=".pdf"
            ref={fileInputRef}
            className="hidden"
            id="pdf-upload"
            onChange={handleFileChange}
          />
          <label htmlFor="pdf-upload" className="py-2 px-3 bg-primary/10 text-primary border border-primary/20 rounded-lg text-sm cursor-pointer transition-colors duration-200 hover:bg-primary/20">
            {loading ? '处理中...' : '📤 选择 PDF 上传'}
          </label>
          <input
            type="text"
            className="flex-1 min-w-[200px] py-2 px-3 bg-muted border border-border rounded-lg text-foreground text-sm focus:outline-none focus:border-primary/30"
            placeholder="输入 PDF 链接或 arXiv 摘要页 URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button className="py-2 px-3.5 bg-primary text-primary-foreground border-none rounded-lg text-sm cursor-pointer transition-opacity duration-200 hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed" onClick={handleDownload} disabled={loading || !url.trim()}>
            ⬇️ 下载
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-2.5">
        <div className="text-sm text-muted-foreground font-semibold">解析策略</div>
        <div className="flex gap-2 items-center flex-wrap">
          <select className="py-2 px-2.5 bg-muted border border-border rounded-md text-foreground text-sm" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            <option value="auto">自动选择</option>
            <option value="pymupdf4llm">PyMuPDF4LLM（本地保底）</option>
            <option value="vision">多模态视觉（限速）</option>
          </select>
          <label className="flex items-center gap-2 text-muted-foreground text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={useVision}
              onChange={(e) => setUseVision(e.target.checked)}
            />
            启用视觉辅助
          </label>
          {useVision && (
            <select
              className="py-2 px-2.5 bg-muted border border-border rounded-md text-foreground text-sm"
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

      {error && <div className="text-error text-sm p-2 bg-error/10 rounded-md">{error}</div>}

      <div className="flex flex-col gap-2.5">
        <div className="text-sm text-muted-foreground font-semibold">已下载 PDF</div>
        {files.length === 0 ? (
          <div className="text-center p-8 text-muted-foreground text-sm">暂无 PDF 文件</div>
        ) : (
          <div className="flex flex-col gap-2 max-h-[300px] overflow-y-auto">
            {files.map((f) => (
              <div key={f.file_id} className="flex justify-between items-center py-3 px-3.5 bg-muted border border-border rounded-lg">
                <div className="flex flex-col gap-1 flex-1 min-w-0">
                  <span className="text-foreground text-sm font-medium whitespace-nowrap overflow-hidden text-ellipsis">{f.filename}</span>
                  <span className="text-muted-foreground text-sm">
                    {formatSize(f.size)} · {f.pages ?? '?'} 页 · {f.source}
                  </span>
                </div>
                <div className="flex gap-2 items-center">
                  <button
                    className="py-2 px-3.5 bg-primary text-primary-foreground border-none rounded-lg text-sm cursor-pointer transition-opacity duration-200 hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
                    onClick={() => handleParse(f.file_id)}
                    disabled={parsing === f.file_id}
                  >
                    {parsing === f.file_id ? '解析中...' : '🔍 解析'}
                  </button>
                  <button className="py-1.5 px-3 bg-error/10 text-error border border-error/20 rounded-md text-sm cursor-pointer hover:bg-error/20" onClick={() => handleDelete(f.file_id)}>
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {result && (
        <div className="flex flex-col gap-2.5">
          <div className="text-sm text-muted-foreground font-semibold">解析结果</div>
          <div className="bg-muted border border-border rounded-lg p-4 max-h-[400px] overflow-y-auto">
            <div className="flex gap-2 flex-wrap mb-2.5 pb-2.5 border-b border-border">
              <span className="text-sm text-primary bg-primary/10 px-2 py-0.5 rounded">策略: {result.strategy}</span>
              <span className="text-sm text-primary bg-primary/10 px-2 py-0.5 rounded">页数: {result.pages}</span>
              {result.metadata?.total_pages && (
                <span className="text-sm text-primary bg-primary/10 px-2 py-0.5 rounded">总页数: {result.metadata.total_pages}</span>
              )}
            </div>
            <pre className="text-muted-foreground text-sm leading-relaxed whitespace-pre-wrap font-mono">{result.markdown || result.text}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
