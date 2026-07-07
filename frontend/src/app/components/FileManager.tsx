'use client';

import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { useAppStore } from '../store/useAppStore';
import { apiBase } from '@/lib/api';

interface FileInfo {
  name: string;
  size: number;
  type: string;
  shape?: [number, number];
  insights?: string[];
  source?: 'user_upload' | 'self_collected';
  modified?: number;
  meta?: SelfCollectedMeta;
}

interface SelfCollectedMeta {
  url?: string;
  downloaded_at?: number;
  content_type?: string;
  source_query?: string;
  http_status?: number;
  error?: string;
}

interface FileManagerProps {
  taskId?: string | null;
}

type TabKey = 'user_upload' | 'self_collected' | 'knowledge_base';

export default function FileManager({ taskId }: FileManagerProps) {
  const [tab, setTab] = useState<TabKey>('user_upload');
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [selfIndex, setSelfIndex] = useState<SelfCollectedMeta[]>([]);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(false);
  const selectedFilesRaw = useAppStore((s) => s.selectedFiles);
  const selectedFiles: Set<string> = selectedFilesRaw instanceof Set
    ? selectedFilesRaw
    : new Set(Array.isArray(selectedFilesRaw) ? selectedFilesRaw : []);
  const toggleFile = useAppStore((s) => s.toggleFileSelection);
  const selectAll = useAppStore((s) => s.selectAllFiles);
  const clearSelection = useAppStore((s) => s.clearFileSelection);
  const activeProject = useAppStore((s) => s.projects.find((p) => p.id === s.activeProjectId));
  const projectName = activeProject?.name || '';

  const loadUserFiles = async () => {
    setLoading(true);
    try {
      const url = new URL(apiBase() + '/data/files');
      if (projectName) url.searchParams.set('project_name', projectName);
      url.searchParams.set('source', 'user_upload');
      const res = await fetch(url.toString());
      if (res.ok) {
        const data = await res.json();
        setFiles(Array.isArray(data) ? data : []);
      }
    } catch (err) {
      console.error('[FileManager] loadUserFiles error:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadSelfCollected = async () => {
    setLoading(true);
    try {
      const url = new URL(apiBase() + '/data/self-collected');
      if (projectName) url.searchParams.set('project_name', projectName);
      const res = await fetch(url.toString());
      if (res.ok) {
        const data = await res.json();
        const fileList = Array.isArray(data?.files) ? data.files : [];
        const idx = Array.isArray(data?.index) ? data.index : [];
        setFiles(fileList);
        setSelfIndex(idx);
      }
    } catch (err) {
      console.error('[FileManager] loadSelfCollected error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (tab === 'user_upload') loadUserFiles();
    else if (tab === 'self_collected') loadSelfCollected();
  }, [tab, projectName]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList?.length) return;
    setUploading(true);
    for (const file of Array.from(fileList)) {
      const formData = new FormData();
      formData.append('file', file);
      if (taskId) formData.append('task_id', taskId);
      try {
        const url = new URL(apiBase() + '/data/upload');
        if (projectName) url.searchParams.set('project_name', projectName);
        url.searchParams.set('source', 'user_upload');
        await fetch(url.toString(), { method: 'POST', body: formData });
      } catch {}
    }
    setUploading(true ? true : false);
    setUploading(false);
    loadUserFiles();
  };

  const handleDelete = async (fileName: string, source: 'user_upload' | 'self_collected' = 'user_upload') => {
    if (!confirm(`确定删除文件 "${fileName}" 吗？`)) return;
    try {
      const url = new URL(apiBase() + '/data/files/' + encodeURIComponent(fileName));
      if (projectName) url.searchParams.set('project_name', projectName);
      url.searchParams.set('source', source);
      await fetch(url.toString(), { method: 'DELETE' });
      clearSelection();
      if (source === 'user_upload') loadUserFiles();
      else loadSelfCollected();
    } catch {}
  };

  const handleBatchDelete = async () => {
    if (!selectedFiles.size) return;
    if (!confirm(`确定批量删除 ${selectedFiles.size} 个文件吗？`)) return;
    for (const name of Array.from(selectedFiles)) {
      try {
        const url = new URL(apiBase() + '/data/files/' + encodeURIComponent(name));
        if (projectName) url.searchParams.set('project_name', projectName);
        url.searchParams.set('source', 'user_upload');
        await fetch(url.toString(), { method: 'DELETE' });
      } catch {}
    }
    clearSelection();
    loadUserFiles();
  };

  const allSelected = files.length > 0 && files.every((f) => selectedFiles.has(f.name));

  return (
    <div className="bg-[#1E293B] border border-[#334155] rounded-[14px] p-[1.2rem]">
      <div className="flex justify-between items-center mb-2">
        <span className="text-[1rem] text-[#F8FAFC] font-semibold">📁 数据文件管理{projectName ? ` · ${projectName}` : ''}</span>
        {tab === 'user_upload' && (
          <label className="inline-flex items-center gap-2 py-2 px-4 bg-[#2DD4BF] text-[#F8FAFC] rounded-[8px] cursor-pointer text-[0.9375rem] font-semibold hover:-translate-y-[1px] transition-transform duration-200 disabled:opacity-60 disabled:cursor-not-allowed">
            {uploading ? '上传中...' : '📤 批量上传'}
            <input
              type="file"
              accept=".csv,.xlsx,.xls,.json,.txt,.tsv,.parquet,.png,.jpg,.jpeg,.pdf"
              multiple
              onChange={handleUpload}
              className="hidden"
              disabled={uploading}
            />
          </label>
        )}
      </div>

      <div className="flex gap-[0.3rem] mb-4 border-b border-[#334155] pb-0">
        <button
          className={cn(
            'py-[0.55rem] px-4 bg-transparent text-[#94A3B8] border-none border-b-2 border-transparent cursor-pointer text-[0.9375rem] font-medium transition-all duration-200 -mb-px hover:text-[#F8FAFC]',
            tab === 'user_upload' && 'text-[#2DD4BF] border-b-[#2DD4BF] font-semibold'
          )}
          onClick={() => setTab('user_upload')}
        >
          📤 用户上传
        </button>
        <button
          className={cn(
            'py-[0.55rem] px-4 bg-transparent text-[#94A3B8] border-none border-b-2 border-transparent cursor-pointer text-[0.9375rem] font-medium transition-all duration-200 -mb-px hover:text-[#F8FAFC]',
            tab === 'self_collected' && 'text-[#2DD4BF] border-b-[#2DD4BF] font-semibold'
          )}
          onClick={() => setTab('self_collected')}
        >
          🌐 系统自收集
        </button>
        <button
          className={cn(
            'py-[0.55rem] px-4 bg-transparent text-[#94A3B8] border-none border-b-2 border-transparent cursor-pointer text-[0.9375rem] font-medium transition-all duration-200 -mb-px hover:text-[#F8FAFC]',
            tab === 'knowledge_base' && 'text-[#2DD4BF] border-b-[#2DD4BF] font-semibold'
          )}
          onClick={() => setTab('knowledge_base')}
        >
          📚 知识库
        </button>
      </div>

      {tab === 'user_upload' && (
        <>
          <div className="text-[#64748B] text-[0.875rem] mb-4">
            支持 CSV · Excel · JSON · 图片 · PDF · 可多选批量删除
            {projectName ? ' · 文件将保存到项目目录' : ' · 全局文件池'}
          </div>

          {files.length > 0 && (
            <div className="flex items-center gap-4 mb-[0.6rem] py-[0.4rem] px-[0.6rem] bg-black/15 rounded-[8px]">
              <label className="flex items-center gap-[0.4rem] text-[#94A3B8] text-[0.9375rem] cursor-pointer">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={() => allSelected ? clearSelection() : selectAll(files.map((f) => f.name))}
                  className="accent-[#3498db] w-4 h-4"
                />
                <span>全选</span>
              </label>
              {selectedFiles.size > 0 && (
                <button className="py-[0.4rem] px-[0.8rem] bg-[rgba(248,113,113,0.15)] text-[#e74c3c] border border-[rgba(248,113,113,0.15)] rounded-[6px] cursor-pointer text-[0.9375rem] font-semibold transition-all duration-200 hover:bg-[rgba(248,113,113,0.15)]" onClick={handleBatchDelete}>
                  🗑️ 删除选中 ({selectedFiles.size})
                </button>
              )}
            </div>
          )}

          {loading && files.length === 0 && <div className="text-center p-8 text-[#475569] text-[0.9375rem]">加载中...</div>}
          {files.length === 0 && !loading && (
            <div className="text-center p-8 text-[#475569] text-[0.9375rem]">暂无用户上传文件，请上传数据文件</div>
          )}

          <div className="flex flex-col gap-2">
            {files.map((f) => (
              <div key={f.name} className="flex items-center gap-[0.8rem] p-[0.7rem] bg-black/20 rounded-[8px] flex-wrap">
                <input
                  type="checkbox"
                  className="accent-[#3498db] w-4 h-4 cursor-pointer"
                  checked={selectedFiles.has(f.name)}
                  onChange={() => toggleFile(f.name)}
                />
                <span className="text-[0.875rem] py-[0.2rem] px-2 bg-[rgba(155,89,182,0.2)] rounded-[4px] text-[#9b59b6] font-semibold min-w-[50px] text-center">{f.type}</span>
                <div className="flex-1">
                  <span className="block text-[0.9375rem] text-[#CBD5E1]">{f.name}</span>
                  <span className="block text-[0.78rem] text-[#64748B] mt-[0.2rem]">
                    {typeof f.size === 'number' ? `${(f.size / 1024).toFixed(1)} KB` : '未知大小'}
                    {f.shape ? ` · ${f.shape[0]}行 x ${f.shape[1]}列` : ''}
                  </span>
                </div>
                {f.insights && f.insights.length > 0 && (
                  <div className="flex gap-[0.3rem] flex-wrap">
                    {f.insights.slice(0, 2).map((ins, j) => (
                      <span key={j} className="text-[0.72rem] py-[0.15rem] px-2 bg-[rgba(74,222,128,0.15)] rounded-[10px] text-[#2ecc71]">{ins}</span>
                    ))}
                  </div>
                )}
                <button
                  className="py-[0.3rem] px-[0.6rem] bg-[rgba(248,113,113,0.15)] text-[#e74c3c] border border-[rgba(248,113,113,0.15)] rounded-[6px] cursor-pointer text-[0.875rem] transition-all duration-200 hover:bg-[rgba(248,113,113,0.15)] ml-2 shrink-0"
                  onClick={() => handleDelete(f.name, 'user_upload')}
                  title="删除"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === 'self_collected' && (
        <>
          <div className="text-[#64748B] text-[0.875rem] mb-4">
            系统在任务执行期间自动下载的公开数据（Kaggle / UCI / arXiv / 政府开放数据等）。
            带原 URL 和来源关键词，点击文件名跳转。
          </div>

          {loading && files.length === 0 && <div className="text-center p-8 text-[#475569] text-[0.9375rem]">加载中...</div>}
          {files.length === 0 && !loading && (
            <div className="text-center p-8 text-[#475569] text-[0.9375rem]">
              暂无自收集文件。提交任务时启用「自主搜集数据」即可。
            </div>
          )}

          <div className="flex flex-col gap-2">
            {files.map((f) => {
              const meta = f.meta;
              return (
                <div key={f.name} className="flex items-center gap-[0.8rem] p-[0.7rem] bg-black/20 rounded-[8px] flex-wrap">
                  <span className="inline-block text-[0.72rem] py-[0.15rem] px-2 bg-[rgba(139,92,246,0.15)] text-[#8B5CF6] rounded-[10px] font-medium">🌐 自收集</span>
                  <span className="text-[0.875rem] py-[0.2rem] px-2 bg-[rgba(155,89,182,0.2)] rounded-[4px] text-[#9b59b6] font-semibold min-w-[50px] text-center">{f.type}</span>
                  <div className="flex-1">
                    <span className="block text-[0.9375rem] text-[#CBD5E1]">{f.name}</span>
                    <span className="block text-[0.78rem] text-[#64748B] mt-[0.2rem]">
                      {typeof f.size === 'number' ? `${(f.size / 1024).toFixed(1)} KB` : ''}
                      {meta?.source_query ? ` · 来源: ${meta.source_query}` : ''}
                    </span>
                    {meta?.url && (
                      <span className="text-[0.72rem] text-[#64748B] mt-[0.2rem] block break-all">
                        <a href={meta.url} target="_blank" rel="noopener noreferrer" className="text-[#60A5FA] no-underline hover:underline">
                          {meta.url.length > 60 ? meta.url.slice(0, 60) + '...' : meta.url}
                        </a>
                      </span>
                    )}
                  </div>
                  {meta?.error && (
                    <span className="text-[#e74c3c] text-[0.78rem]">
                      ⚠ {meta.error}
                    </span>
                  )}
                  <button
                    className="py-[0.3rem] px-[0.6rem] bg-[rgba(248,113,113,0.15)] text-[#e74c3c] border border-[rgba(248,113,113,0.15)] rounded-[6px] cursor-pointer text-[0.875rem] transition-all duration-200 hover:bg-[rgba(248,113,113,0.15)] shrink-0"
                    onClick={() => handleDelete(f.name, 'self_collected')}
                    title="删除"
                  >
                    ✕
                  </button>
                </div>
              );
            })}
          </div>

          {selfIndex.length > 0 && (
            <div className="mt-4 text-[0.78rem] text-[#64748B]">
              共索引 {selfIndex.length} 条下载记录（{selfIndex.filter(i => i.error).length} 条失败）
            </div>
          )}
        </>
      )}

      {tab === 'knowledge_base' && (
        <div className="p-6 text-center bg-black/15 rounded-[8px]">
          <p className="text-[#94A3B8] my-2 text-[0.9375rem]">📚 知识库是独立管理的向量数据库系统。</p>
          <p className="text-[#94A3B8] my-2 text-[0.9375rem]">支持全局公共 + 项目私有两级 scope，可与多个任务关联。</p>
          <p className="text-[#64748B] my-2 text-[0.85rem]">
            创建 KB / 上传文档 / 配置嵌入模型 → 任务提交时勾选注入
          </p>
          <a href="#" onClick={(e) => { e.preventDefault(); window.dispatchEvent(new CustomEvent('mm:switch-tab', { detail: 'knowledge' })); }} className="inline-block mt-[0.8rem] py-2 px-4 bg-[#2DD4BF] text-[#0F172A] rounded-[8px] no-underline font-semibold text-[0.9375rem] hover:bg-[#5EEAD4]">
            前往知识库管理 →
          </a>
        </div>
      )}
    </div>
  );
}
