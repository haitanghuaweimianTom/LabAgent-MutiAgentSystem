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
    <div data-design-id="pdf:card" className="bg-card border border-border rounded-xl px-8 py-6 shadow-[var(--shadow-card)] flex flex-col items-center gap-5 mx-auto w-full max-w-[1320px]">
      <div data-design-id="pdf:title" className="text-lg text-foreground font-semibold">📄 PDF 解析中心</div>

      {/* 上传 / 下载 */}
      <section className="flex flex-col items-center gap-2.5 w-full">
        <div data-design-id="pdf:label-upload" className="text-sm text-muted-foreground font-semibold">上传 / 下载 PDF</div>
        <div data-design-id="pdf:row-upload" className="flex gap-4 items-center flex-wrap">
          <input
            type="file"
            accept=".pdf"
            ref={fileInputRef}
            className="hidden"
            id="pdf-upload"
            onChange={handleFileChange}
          />
          <label data-design-id="pdf:btn-upload" htmlFor="pdf-upload" className="inline-flex items-center justify-center gap-3 min-h-[40px] py-2 px-8 bg-primary/10 text-primary border border-primary/20 rounded-lg text-sm cursor-pointer transition-colors hover:bg-primary/20 shrink-0">
            {loading ? '处理中...' : '📤 选择 PDF 上传'}
          </label>
          <input
            data-design-id="pdf:input-url"
            type="text"
            className="flex-1 min-w-[330px] max-w-[630px] h-10 px-5 bg-muted border border-border rounded-lg text-foreground text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 placeholder:text-muted-foreground"
            placeholder="输入 PDF 链接或 arXiv 摘要页 URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button data-design-id="pdf:btn-download" className="inline-flex items-center justify-center gap-3 min-h-[40px] py-2 px-10 bg-primary text-primary-foreground rounded-lg text-sm cursor-pointer transition-opacity hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed shrink-0" onClick={handleDownload} disabled={loading || !url.trim()}>
            ⬇️ 下载
          </button>
        </div>
      </section>

      {/* 解析策略 */}
      <section className="flex flex-col items-center gap-2.5 w-full">
        <div data-design-id="pdf:label-strategy" className="text-sm text-muted-foreground font-semibold">解析策略</div>
        <div data-design-id="pdf:row-strategy" className="flex gap-3 items-center flex-wrap">
          <select data-design-id="pdf:select-strategy" className="h-10 px-5 bg-muted border border-border rounded-lg text-foreground text-sm text-center outline-none focus:border-primary" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            <option value="auto" className="text-center">自动选择</option>
            <option value="pymupdf4llm" className="text-center">PyMuPDF4LLM（本地保底）</option>
            <option value="vision" className="text-center">多模态视觉（限速）</option>
          </select>
          <label data-design-id="pdf:vision-toggle" className="flex items-center gap-3 text-muted-foreground text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={useVision}
              onChange={(e) => setUseVision(e.target.checked)}
            />
            启用视觉辅助
          </label>
          {useVision && (
            <select
              data-design-id="pdf:select-provider"
              className="h-10 px-5 bg-muted border border-border rounded-lg text-foreground text-sm outline-none focus:border-primary"
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
      </section>

      {error && <div className="text-error text-sm px-5 py-2.5 bg-error/10 rounded-md">{error}</div>}

      {/* 已下载列表 */}
      <section className="flex flex-col items-center gap-2.5 w-full">
        <div data-design-id="pdf:label-files" className="text-sm text-muted-foreground font-semibold">已下载 PDF</div>
        {files.length === 0 ? (
          <div className="flex flex-col items-center justify-center text-center py-16 text-muted-foreground text-sm">
            <span className="text-4xl opacity-40 mb-2">📄</span>
            暂无 PDF 文件
          </div>
        ) : (
          <div className="flex flex-col gap-3 max-h-[300px] overflow-y-auto">
            {files.map((f) => (
              <div key={f.file_id} className="flex justify-between items-center gap-3 py-3 px-7 bg-muted border border-border rounded-lg">
                <div className="flex flex-col gap-1 flex-1 min-w-0">
                  <span className="text-foreground text-sm font-medium truncate" title={f.filename}>{f.filename}</span>
                  <span className="text-muted-foreground text-sm">
                    {formatSize(f.size)} · {f.pages ?? '?'} 页 · {f.source}
                  </span>
                </div>
                <div className="flex gap-3 items-center shrink-0">
                  <button
                    data-design-id="pdf:btn-parse"
                    className="inline-flex items-center justify-center gap-3 min-h-[36px] py-2 px-8 bg-primary text-primary-foreground rounded-lg text-sm cursor-pointer transition-opacity hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
                    onClick={() => handleParse(f.file_id)}
                    disabled={parsing === f.file_id}
                  >
                    {parsing === f.file_id ? '解析中...' : '🔍 解析'}
                  </button>
                  <button className="inline-flex items-center justify-center leading-tight py-1.5 px-6 min-h-[30px] bg-error/10 text-error border border-error/20 rounded-md text-sm cursor-pointer hover:bg-error/15" onClick={() => handleDelete(f.file_id)}>
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {result && (
        <section className="flex flex-col items-center gap-2.5 w-full">
          <div className="text-sm text-muted-foreground font-semibold">解析结果</div>
          <div className="bg-muted border border-border rounded-lg px-6 py-4 max-h-[400px] overflow-y-auto">
            <div className="flex gap-3 flex-wrap mb-2.5 pb-2.5 border-b border-border">
              <span className="text-sm text-primary bg-primary/10 px-2 py-0.5 rounded">策略: {result.strategy}</span>
              <span className="text-sm text-primary bg-primary/10 px-2 py-0.5 rounded">页数: {result.pages}</span>
              {result.metadata?.total_pages && (
                <span className="text-sm text-primary bg-primary/10 px-2 py-0.5 rounded">总页数: {result.metadata.total_pages}</span>
              )}
            </div>
            <pre className="text-muted-foreground text-sm leading-relaxed whitespace-pre-wrap font-mono">{result.markdown || result.text}</pre>
          </div>
        </section>
      )}
    </div>
  );
}
