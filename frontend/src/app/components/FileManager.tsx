'use client';

import { useState, useEffect } from 'react';
import styles from './FileManager.module.css';
import { useAppStore } from '../store/useAppStore';

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

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

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
    // knowledge_base tab 不拉数据（独立管理）
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.title}>📁 数据文件管理{projectName ? ` · ${projectName}` : ''}</span>
        {tab === 'user_upload' && (
          <label className={styles.uploadBtn}>
            {uploading ? '上传中...' : '📤 批量上传'}
            <input
              type="file"
              accept=".csv,.xlsx,.xls,.json,.txt,.tsv,.parquet,.png,.jpg,.jpeg,.pdf"
              multiple
              onChange={handleUpload}
              style={{ display: 'none' }}
              disabled={uploading}
            />
          </label>
        )}
      </div>

      {/* v5.4.0: 3-Tab 切换 */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${tab === 'user_upload' ? styles.tabActive : ''}`}
          onClick={() => setTab('user_upload')}
        >
          📤 用户上传
        </button>
        <button
          className={`${styles.tab} ${tab === 'self_collected' ? styles.tabActive : ''}`}
          onClick={() => setTab('self_collected')}
        >
          🌐 系统自收集
        </button>
        <button
          className={`${styles.tab} ${tab === 'knowledge_base' ? styles.tabActive : ''}`}
          onClick={() => setTab('knowledge_base')}
        >
          📚 知识库
        </button>
      </div>

      {/* Tab: 用户上传 */}
      {tab === 'user_upload' && (
        <>
          <div className={styles.hint}>
            支持 CSV · Excel · JSON · 图片 · PDF · 可多选批量删除
            {projectName ? ' · 文件将保存到项目目录' : ' · 全局文件池'}
          </div>

          {files.length > 0 && (
            <div className={styles.batchBar}>
              <label className={styles.checkAll}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={() => allSelected ? clearSelection() : selectAll(files.map((f) => f.name))}
                />
                <span>全选</span>
              </label>
              {selectedFiles.size > 0 && (
                <button className={styles.batchDeleteBtn} onClick={handleBatchDelete}>
                  🗑️ 删除选中 ({selectedFiles.size})
                </button>
              )}
            </div>
          )}

          {loading && files.length === 0 && <div className={styles.empty}>加载中...</div>}
          {files.length === 0 && !loading && (
            <div className={styles.empty}>暂无用户上传文件，请上传数据文件</div>
          )}

          <div className={styles.fileList}>
            {files.map((f) => (
              <div key={f.name} className={styles.fileItem}>
                <input
                  type="checkbox"
                  className={styles.fileCheck}
                  checked={selectedFiles.has(f.name)}
                  onChange={() => toggleFile(f.name)}
                />
                <span className={styles.fileIcon}>{f.type}</span>
                <div className={styles.fileInfo}>
                  <span className={styles.fileName}>{f.name}</span>
                  <span className={styles.fileSize}>
                    {typeof f.size === 'number' ? `${(f.size / 1024).toFixed(1)} KB` : '未知大小'}
                    {f.shape ? ` · ${f.shape[0]}行 x ${f.shape[1]}列` : ''}
                  </span>
                </div>
                {f.insights && f.insights.length > 0 && (
                  <div className={styles.insights}>
                    {f.insights.slice(0, 2).map((ins, j) => (
                      <span key={j} className={styles.insightTag}>{ins}</span>
                    ))}
                  </div>
                )}
                <button
                  className={styles.deleteBtn}
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

      {/* Tab: 系统自收集 */}
      {tab === 'self_collected' && (
        <>
          <div className={styles.hint}>
            系统在任务执行期间自动下载的公开数据（Kaggle / UCI / arXiv / 政府开放数据等）。
            带原 URL 和来源关键词，点击文件名跳转。
          </div>

          {loading && files.length === 0 && <div className={styles.empty}>加载中...</div>}
          {files.length === 0 && !loading && (
            <div className={styles.empty}>
              暂无自收集文件。提交任务时启用「自主搜集数据」即可。
            </div>
          )}

          <div className={styles.fileList}>
            {files.map((f) => {
              const meta = f.meta;
              return (
                <div key={f.name} className={styles.fileItem}>
                  <span className={`${styles.sourceBadge} ${styles.sourceBadgeSelf}`}>🌐 自收集</span>
                  <span className={styles.fileIcon}>{f.type}</span>
                  <div className={styles.fileInfo}>
                    <span className={styles.fileName}>{f.name}</span>
                    <span className={styles.fileSize}>
                      {typeof f.size === 'number' ? `${(f.size / 1024).toFixed(1)} KB` : ''}
                      {meta?.source_query ? ` · 来源: ${meta.source_query}` : ''}
                    </span>
                    {meta?.url && (
                      <span className={styles.metaUrl}>
                        <a href={meta.url} target="_blank" rel="noopener noreferrer">
                          {meta.url.length > 60 ? meta.url.slice(0, 60) + '...' : meta.url}
                        </a>
                      </span>
                    )}
                  </div>
                  {meta?.error && (
                    <span style={{ color: '#e74c3c', fontSize: '0.78rem' }}>
                      ⚠ {meta.error}
                    </span>
                  )}
                  <button
                    className={styles.deleteBtn}
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
            <div style={{ marginTop: '1rem', fontSize: '0.78rem', color: '#64748B' }}>
              共索引 {selfIndex.length} 条下载记录（{selfIndex.filter(i => i.error).length} 条失败）
            </div>
          )}
        </>
      )}

      {/* Tab: 知识库（跳转提示） */}
      {tab === 'knowledge_base' && (
        <div className={styles.kbHint}>
          <p>📚 知识库是独立管理的向量数据库系统。</p>
          <p>支持全局公共 + 项目私有两级 scope，可与多个任务关联。</p>
          <p style={{ fontSize: '0.85rem', color: '#64748B' }}>
            创建 KB / 上传文档 / 配置嵌入模型 → 任务提交时勾选注入
          </p>
          <a href="#" onClick={(e) => { e.preventDefault(); window.dispatchEvent(new CustomEvent('mm:switch-tab', { detail: 'knowledge' })); }}>
            前往知识库管理 →
          </a>
        </div>
      )}
    </div>
  );
}