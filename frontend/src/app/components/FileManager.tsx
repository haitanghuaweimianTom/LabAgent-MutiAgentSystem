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
}

interface FileManagerProps {
  taskId?: string | null;
}

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

export default function FileManager({ taskId }: FileManagerProps) {
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(false);
  const selectedFiles = useAppStore((s) => s.selectedFiles);
  const toggleFile = useAppStore((s) => s.toggleFileSelection);
  const selectAll = useAppStore((s) => s.selectAllFiles);
  const clearSelection = useAppStore((s) => s.clearFileSelection);

  const loadFiles = async () => {
    setLoading(true);
    try {
      const res = await fetch(apiBase() + '/data/files');
      if (res.ok) setFiles(await res.json());
    } catch {} finally { setLoading(false); }
  };

  useEffect(() => { loadFiles(); }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList?.length) return;
    setUploading(true);
    for (const file of Array.from(fileList)) {
      const formData = new FormData();
      formData.append('file', file);
      if (taskId) formData.append('task_id', taskId);
      try {
        await fetch(apiBase() + '/data/upload', { method: 'POST', body: formData });
      } catch {}
    }
    setUploading(false);
    loadFiles();
  };

  const handleDelete = async (fileName: string) => {
    if (!confirm(`确定删除文件 "${fileName}" 吗？`)) return;
    try {
      await fetch(apiBase() + '/data/files/' + encodeURIComponent(fileName), { method: 'DELETE' });
      clearSelection();
      loadFiles();
    } catch {}
  };

  const handleBatchDelete = async () => {
    if (!selectedFiles.size) return;
    if (!confirm(`确定批量删除 ${selectedFiles.size} 个文件吗？`)) return;
    for (const name of Array.from(selectedFiles)) {
      try {
        await fetch(apiBase() + '/data/files/' + encodeURIComponent(name), { method: 'DELETE' });
      } catch {}
    }
    clearSelection();
    loadFiles();
  };

  const allSelected = files.length > 0 && files.every((f) => selectedFiles.has(f.name));

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.title}>📁 数据文件管理</span>
        <label className={styles.uploadBtn}>
          {uploading ? '上传中...' : '📤 批量上传'}
          <input type="file" accept=".csv,.xlsx,.xls,.json,.txt,.tsv,.parquet,.png,.jpg,.jpeg,.pdf" multiple onChange={handleUpload} style={{ display: 'none' }} disabled={uploading} />
        </label>
      </div>
      <div className={styles.hint}>支持 CSV · Excel · JSON · 图片 · PDF · 可多选批量删除</div>

      {files.length > 0 && (
        <div className={styles.batchBar}>
          <label className={styles.checkAll}>
            <input type="checkbox" checked={allSelected} onChange={() => allSelected ? clearSelection() : selectAll(files.map((f) => f.name))} />
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
      {files.length === 0 && !loading && <div className={styles.empty}>暂无文件，请上传数据文件</div>}

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
                {(f.size / 1024).toFixed(1)} KB
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
            <button className={styles.deleteBtn} onClick={() => handleDelete(f.name)} title="删除">✕</button>
          </div>
        ))}
      </div>
    </div>
  );
}
