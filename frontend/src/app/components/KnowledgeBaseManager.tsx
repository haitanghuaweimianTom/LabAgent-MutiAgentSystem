'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAppStore } from '../store/useAppStore';
import { apiBase } from '@/lib/api';
import { cn } from '@/lib/utils';

interface FileMetadata {
  name: string;
  size: number;
  ext: string;
  path: string;
}

interface KnowledgeItem {
  id: string;
  type: 'file' | 'note' | 'url' | 'sitemap' | 'directory';
  content: string | FileMetadata;
  source?: string;
  metadata?: Record<string, any>;
  processingStatus?: 'pending' | 'processing' | 'completed' | 'failed';
  created_at?: number;
  updated_at?: number;
}

interface KnowledgeBase {
  id: string;
  name: string;
  description?: string;
  item_count?: number;
  created_at?: number;
  updated_at?: number;
  embedding_model?: Record<string, any>;
  reranker_model?: Record<string, any> | null;
  scope?: 'global' | 'project';
  project_name?: string | null;
}

interface SearchResult {
  id: string;
  title: string;
  content: string;
  source?: string;
  score: number;
  metadata?: Record<string, any>;
}

const TABS = [
  { key: 'file', label: 'Files' },
  { key: 'note', label: 'Notes' },
  { key: 'url', label: 'URLs' },
  { key: 'sitemap', label: 'Sitemaps' },
  { key: 'directory', label: 'Directories' },
] as const;

type TabKey = typeof TABS[number]['key'];

function isFileMeta(content: string | FileMetadata): content is FileMetadata {
  return typeof content === 'object' && content !== null && 'name' in content;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function statusIcon(status?: string): string {
  switch (status) {
    case 'completed': return '✅';
    case 'failed': return '❌';
    case 'processing': return '⏳';
    case 'pending': return '🕐';
    default: return '✅';
  }
}

function typeIcon(type: string): string {
  switch (type) {
    case 'file': return '📄';
    case 'note': return '📝';
    case 'url': return '🔗';
    case 'sitemap': return '🗺️';
    case 'directory': return '📁';
    default: return '📄';
  }
}

export default function KnowledgeBaseManager() {
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [activeBaseId, setActiveBaseId] = useState<string | null>(null);
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [activeTab, setActiveTab] = useState<TabKey>('file');
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');

  const [scopeFilter, setScopeFilter] = useState<'all' | 'global' | 'project'>('all');
  const activeProject = useAppStore((s) => s.projects.find((p) => p.id === s.activeProjectId));
  const projectName = activeProject?.name || '';

  const [showCreateBase, setShowCreateBase] = useState(false);
  const [newBaseName, setNewBaseName] = useState('');
  const [newBaseScope, setNewBaseScope] = useState<'global' | 'project'>('global');
  const [newBaseProjectName, setNewBaseProjectName] = useState('');

  const [showRenameBase, setShowRenameBase] = useState(false);
  const [renameBaseName, setRenameBaseName] = useState('');

  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [showAddNote, setShowAddNote] = useState(false);
  const [noteContent, setNoteContent] = useState('');

  const [editingItem, setEditingItem] = useState<KnowledgeItem | null>(null);
  const [replacingItem, setReplacingItem] = useState<KnowledgeItem | null>(null);
  const replaceFileInputRef = useRef<HTMLInputElement>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);

  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(new Set());

  const [showSettings, setShowSettings] = useState(false);
  const [settingsEmbedding, setSettingsEmbedding] = useState('tfidf');
  const [settingsEmbeddingModel, setSettingsEmbeddingModel] = useState('');
  const [settingsEmbeddingApiKey, setSettingsEmbeddingApiKey] = useState('');
  const [settingsEmbeddingBaseUrl, setSettingsEmbeddingBaseUrl] = useState('');
  const [settingsReranker, setSettingsReranker] = useState('none');
  const [settingsRerankerModel, setSettingsRerankerModel] = useState('');
  const [settingsRerankerApiKey, setSettingsRerankerApiKey] = useState('');
  const [settingsRerankerBaseUrl, setSettingsRerankerBaseUrl] = useState('');

  const activeBase = bases.find(b => b.id === activeBaseId);

  const showMsg = useCallback((text: string, isError = false) => {
    setMsg(text);
    setTimeout(() => setMsg(''), 3000);
  }, []);

  const loadBases = useCallback(async () => {
    try {
      const url = new URL(apiBase() + '/knowledge/bases');
      if (scopeFilter !== 'all') {
        url.searchParams.set('scope', scopeFilter);
        if (scopeFilter === 'project' && projectName) {
          url.searchParams.set('project_name', projectName);
        }
      }
      const res = await fetch(url.toString());
      if (res.ok) {
        const data = await res.json();
        const list: KnowledgeBase[] = data.bases || [];
        setBases(list);
        if (list.length > 0 && !activeBaseId) {
          setActiveBaseId(list[0].id);
        } else if (list.length === 0) {
          setActiveBaseId(null);
        }
      }
    } catch {
      showMsg('加载知识库列表失败', true);
    }
  }, [activeBaseId, scopeFilter, projectName, showMsg]);

  const loadItems = useCallback(async (baseId: string | null) => {
    if (!baseId) { setItems([]); return; }
    try {
      const res = await fetch(apiBase() + `/knowledge/bases/${baseId}/items`);
      if (res.ok) {
        const data = await res.json();
        setItems(data.items || []);
      }
    } catch {
      showMsg('加载条目失败', true);
    }
  }, [showMsg]);

  useEffect(() => { loadBases(); }, [loadBases]);

  useEffect(() => {
    if (activeBaseId) {
      loadItems(activeBaseId);
    }
  }, [activeBaseId, loadItems]);

  useEffect(() => {
    setSelectedItemIds(new Set());
  }, [activeBaseId, activeTab]);

  const handleCreateBase = async () => {
    const name = newBaseName.trim();
    if (!name) { showMsg('名称不能为空', true); return; }
    if (newBaseScope === 'project' && !newBaseProjectName.trim()) {
      showMsg('项目私有 KB 必须指定项目名', true);
      return;
    }
    try {
      const body: any = { name, scope: newBaseScope };
      if (newBaseScope === 'project') {
        body.project_name = newBaseProjectName.trim();
      }
      const res = await fetch(apiBase() + '/knowledge/bases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.success && data.base) {
        showMsg(`知识库 "${name}" 已创建 (scope=${newBaseScope})`);
        setShowCreateBase(false);
        setNewBaseName('');
        setNewBaseScope('global');
        setNewBaseProjectName('');
        setBases(prev => [...prev, data.base]);
        setActiveBaseId(data.base.id);
      } else {
        showMsg(data.detail || '创建失败', true);
      }
    } catch {
      showMsg('创建失败', true);
    }
  };

  const handleRenameBase = async () => {
    const name = renameBaseName.trim();
    if (!name || !activeBaseId) { showMsg('名称不能为空', true); return; }
    try {
      const res = await fetch(apiBase() + `/knowledge/bases/${activeBaseId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (data.success) {
        showMsg('重命名成功');
        setShowRenameBase(false);
        setBases(prev => prev.map(b => b.id === activeBaseId ? { ...b, name } : b));
      } else {
        showMsg(data.detail || '重命名失败', true);
      }
    } catch {
      showMsg('重命名失败', true);
    }
  };

  const handleDeleteBase = async (baseId: string) => {
    if (!confirm('确定要删除该知识库吗？此操作不可撤销。')) return;
    try {
      const res = await fetch(apiBase() + `/knowledge/bases/${baseId}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) {
        showMsg('知识库已删除');
        setBases(prev => prev.filter(b => b.id !== baseId));
        if (activeBaseId === baseId) {
          const remaining = bases.filter(b => b.id !== baseId);
          setActiveBaseId(remaining.length > 0 ? remaining[0].id : null);
        }
      } else {
        showMsg(data.detail || '删除失败', true);
      }
    } catch {
      showMsg('删除失败', true);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length || !activeBaseId) return;
    setUploading(true);
    for (const file of Array.from(files)) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await fetch(apiBase() + `/knowledge/upload?base_id=${activeBaseId}&chunk_size=500&overlap=50`, {
          method: 'POST',
          body: formData,
        });
        const data = await res.json();
        if (data.success) {
          showMsg(`✓ 已上传 ${data.filename}`);
          loadItems(activeBaseId);
          loadBases();
        } else {
          showMsg(`✗ ${file.name}: ${data.detail || '上传失败'}`, true);
        }
      } catch {
        showMsg(`✗ ${file.name}: 上传失败`, true);
      }
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleAddNote = async () => {
    const content = noteContent.trim();
    if (!content || !activeBaseId) { showMsg('内容不能为空', true); return; }

    const isEdit = editingItem !== null;
    const url = isEdit
      ? apiBase() + `/knowledge/bases/${activeBaseId}/items/${editingItem.id}`
      : apiBase() + `/knowledge/bases/${activeBaseId}/items`;
    const method = isEdit ? 'PUT' : 'POST';

    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'note', content }),
      });
      const data = await res.json();
      if (data.success) {
        showMsg(isEdit ? '笔记已更新' : '笔记已添加');
        setShowAddNote(false);
        setNoteContent('');
        setEditingItem(null);
        loadItems(activeBaseId);
        loadBases();
      } else {
        showMsg(data.detail || (isEdit ? '更新失败' : '添加失败'), true);
      }
    } catch {
      showMsg(isEdit ? '更新失败' : '添加失败', true);
    }
  };

  const openEditNote = (item: KnowledgeItem) => {
    setEditingItem(item);
    setNoteContent(typeof item.content === 'string' ? item.content : '');
    setShowAddNote(true);
  };

  const closeAddNoteModal = () => {
    setShowAddNote(false);
    setNoteContent('');
    setEditingItem(null);
  };

  const handleReplaceFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!activeBaseId || !replacingItem) return;
    const files = e.target.files;
    if (!files?.length) return;

    const file = files[0];
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(
        apiBase() + `/knowledge/bases/${activeBaseId}/items/${replacingItem.id}/file`,
        { method: 'PUT', body: formData }
      );
      const data = await res.json();
      if (data.success) {
        showMsg(`文件已替换为 ${data.filename || file.name}`);
        loadItems(activeBaseId);
        loadBases();
      } else {
        showMsg(data.detail || '替换失败', true);
      }
    } catch {
      showMsg('替换失败', true);
    } finally {
      setReplacingItem(null);
      if (replaceFileInputRef.current) replaceFileInputRef.current.value = '';
    }
  };

  const triggerReplaceFile = (item: KnowledgeItem) => {
    setReplacingItem(item);
    setTimeout(() => {
      replaceFileInputRef.current?.click();
    }, 0);
  };

  const handleDeleteItem = async (itemId: string) => {
    if (!activeBaseId) return;
    if (!confirm('确定要删除该条目吗？')) return;
    try {
      const res = await fetch(apiBase() + `/knowledge/bases/${activeBaseId}/items/${itemId}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) {
        showMsg('条目已删除');
        loadItems(activeBaseId);
        loadBases();
      } else {
        showMsg(data.detail || '删除失败', true);
      }
    } catch {
      showMsg('删除失败', true);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim() || !activeBaseId) return;
    setSearching(true);
    try {
      const res = await fetch(apiBase() + `/knowledge/bases/${activeBaseId}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery.trim(), top_k: 5, min_score: 0.0 }),
      });
      const data = await res.json();
      setSearchResults(data.results || []);
      setShowSearch(true);
    } catch {
      showMsg('搜索失败', true);
    } finally {
      setSearching(false);
    }
  };

  const filteredItems = items.filter(i => i.type === activeTab);

  const toggleSelectItem = (itemId: string) => {
    setSelectedItemIds(prev => {
      const next = new Set(prev);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  };

  const selectAllItems = () => {
    setSelectedItemIds(new Set(filteredItems.map(i => i.id)));
  };

  const clearSelection = () => {
    setSelectedItemIds(new Set());
  };

  const openSettings = async () => {
    if (!activeBaseId) return;
    try {
      const res = await fetch(apiBase() + `/knowledge/bases/${activeBaseId}`);
      if (!res.ok) throw new Error('加载配置失败');
      const fullBase = await res.json();
      const emb = fullBase.embedding_model || { type: 'tfidf' };
      const rerank = fullBase.reranker_model;
      setSettingsEmbedding(emb.type || 'tfidf');
      setSettingsEmbeddingModel(emb.model_name || '');
      setSettingsEmbeddingApiKey(emb.api_key || '');
      setSettingsEmbeddingBaseUrl(emb.base_url || '');
      setSettingsReranker(rerank?.type || 'none');
      setSettingsRerankerModel(rerank?.model_name || '');
      setSettingsRerankerApiKey(rerank?.api_key || '');
      setSettingsRerankerBaseUrl(rerank?.base_url || '');
      setShowSettings(true);
    } catch {
      showMsg('加载配置失败', true);
    }
  };

  const saveSettings = async () => {
    if (!activeBaseId) return;
    const payload: any = {};
    const emb: any = { type: settingsEmbedding };
    if (settingsEmbeddingModel) emb.model_name = settingsEmbeddingModel;
    if (settingsEmbeddingApiKey) emb.api_key = settingsEmbeddingApiKey;
    if (settingsEmbeddingBaseUrl) emb.base_url = settingsEmbeddingBaseUrl;
    payload.embedding_model = emb;

    if (settingsReranker === 'none') {
      payload.reranker_model = null;
    } else {
      const rerank: any = { type: settingsReranker };
      if (settingsRerankerModel) rerank.model_name = settingsRerankerModel;
      if (settingsRerankerApiKey) rerank.api_key = settingsRerankerApiKey;
      if (settingsRerankerBaseUrl) rerank.base_url = settingsRerankerBaseUrl;
      payload.reranker_model = rerank;
    }

    try {
      const res = await fetch(apiBase() + `/knowledge/bases/${activeBaseId}/models`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.success) {
        showMsg('模型配置已保存');
        setShowSettings(false);
        loadBases();
      } else {
        showMsg(data.detail || '保存失败', true);
      }
    } catch {
      showMsg('保存失败', true);
    }
  };

  const handleDeleteSelectedItems = async () => {
    if (!activeBaseId || selectedItemIds.size === 0) return;
    if (!confirm(`确定要删除选中的 ${selectedItemIds.size} 个条目吗？`)) return;
    let successCount = 0;
    for (const itemId of Array.from(selectedItemIds)) {
      try {
        const res = await fetch(apiBase() + `/knowledge/bases/${activeBaseId}/items/${itemId}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) successCount++;
      } catch { /* ignore single failure */ }
    }
    showMsg(`已删除 ${successCount} 个条目`);
    setSelectedItemIds(new Set());
    loadItems(activeBaseId);
    loadBases();
  };

  const handleDownloadItem = async (item: KnowledgeItem) => {
    if (!activeBaseId || item.type !== 'file' || !isFileMeta(item.content)) return;
    try {
      const res = await fetch(apiBase() + `/knowledge/bases/${activeBaseId}/items/${item.id}/download`);
      if (!res.ok) throw new Error('下载失败');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = item.content.name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      showMsg('下载失败', true);
    }
  };

  const handleDownloadSelectedItems = async () => {
    if (!activeBaseId || selectedItemIds.size === 0) return;
    const selectedFiles = filteredItems.filter(
      i => selectedItemIds.has(i.id) && i.type === 'file' && isFileMeta(i.content)
    );
    if (selectedFiles.length === 0) {
      showMsg('选中的条目中无文件可下载', true);
      return;
    }
    let successCount = 0;
    for (const item of selectedFiles) {
      try {
        const res = await fetch(apiBase() + `/knowledge/bases/${activeBaseId}/items/${item.id}/download`);
        if (!res.ok) continue;
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = (item.content as FileMetadata).name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        successCount++;
        await new Promise(r => setTimeout(r, 150));
      } catch { /* ignore single failure */ }
    }
    showMsg(`已下载 ${successCount} 个文件`);
    setSelectedItemIds(new Set());
  };

  const actionBtnBase = "py-[0.4rem] px-[0.8rem] bg-[#334155] border border-[#334155] rounded-[6px] text-[#94A3B8] text-[0.78rem] cursor-pointer transition-all duration-150 whitespace-nowrap hover:bg-[#334155] hover:text-[#F8FAFC]";
  const actionBtnPrimary = "bg-[rgba(74,222,128,0.15)] border-[rgba(74,222,128,0.15)] text-[#2ecc71] hover:bg-[rgba(74,222,128,0.15)]";
  const modalInputBase = "py-[0.6rem] px-[0.6rem] bg-[rgba(0,0,0,0.3)] border border-[#334155] rounded-[8px] text-[#e0e0e0] text-[0.9375rem] outline-none w-full focus:border-[rgba(45,212,191,0.15)]";

  return (
    <div className="flex h-full min-h-[500px] bg-[#1E293B] border border-[#334155] rounded-[14px] overflow-hidden">
      {/* Sidebar */}
      <div className="w-[240px] min-w-[200px] flex flex-col border-r border-[#334155] bg-[rgba(0,0,0,0.2)]">
        <div className="p-4 border-b border-[#334155] flex items-center justify-between">
          <span className="text-[0.95rem] text-[#F8FAFC] font-semibold">📚 知识库</span>
          <button className="py-[0.3rem] px-[0.6rem] bg-[rgba(74,222,128,0.15)] border border-[rgba(74,222,128,0.15)] rounded-[6px] text-[#2ecc71] text-[0.875rem] cursor-pointer font-semibold" onClick={() => setShowCreateBase(true)}>+ 新建</button>
        </div>
        <div className="flex gap-1 py-[0.4rem] px-[0.6rem] border-b border-[#334155]">
          {(['all', 'global', 'project'] as const).map(s => (
            <button
              key={s}
              className={cn(actionBtnBase, scopeFilter === s && actionBtnPrimary)}
              style={{ fontSize: '0.78rem', padding: '0.3rem 0.6rem' }}
              onClick={() => setScopeFilter(s)}
              type="button"
            >
              {s === 'all' ? '全部' : s === 'global' ? '🌐 全局' : '📁 项目'}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {bases.map(base => (
            <div
              key={base.id}
              className={cn('flex items-center justify-between py-[0.6rem] px-[0.8rem] rounded-[8px] cursor-pointer mb-[0.3rem] transition-[background] duration-150 border border-transparent hover:bg-[#1E293B]', base.id === activeBaseId && 'bg-[rgba(45,212,191,0.15)] border-[rgba(45,212,191,0.15)]')}
              onClick={() => { setActiveBaseId(base.id); setShowSearch(false); setSearchResults([]); }}
            >
              <div className="flex flex-col flex-1 min-w-0">
                <span className={cn('text-[#CBD5E1] text-[0.9375rem] font-medium whitespace-nowrap overflow-hidden text-ellipsis', base.id === activeBaseId && 'text-[#F8FAFC]')}>{base.name}</span>
                <span style={{
                  fontSize: '0.7rem',
                  color: base.scope === 'project' ? '#8B5CF6' : '#2DD4BF',
                  marginTop: '0.15rem',
                }}>
                  {base.scope === 'project'
                    ? `📁 ${base.project_name || '项目'}`
                    : '🌐 全局'}
                </span>
              </div>
              <span className="text-[0.8125rem] text-[#94A3B8] bg-[#334155] px-[0.4rem] py-[0.1rem] rounded-[10px] ml-[0.4rem]">{base.item_count ?? 0}</span>
              <button
                className="opacity-0 transition-[opacity] duration-150 ml-[0.3rem] py-[0.1rem] px-[0.3rem] bg-transparent border-none text-[#94A3B8] cursor-pointer text-[0.9375rem] hover:opacity-100"
                onClick={(e) => {
                  e.stopPropagation();
                  const action = window.prompt(`操作: ${base.name}\n1. 重命名\n2. 删除\n请输入数字:`);
                  if (action === '1') {
                    setRenameBaseName(base.name);
                    setShowRenameBase(true);
                  } else if (action === '2') {
                    handleDeleteBase(base.id);
                  }
                }}
              >
                ⋯
              </button>
            </div>
          ))}
          {bases.length === 0 && (
            <div style={{ color: '#666', textAlign: 'center', padding: '2rem 0.5rem', fontSize: '0.85rem' }}>
              暂无知识库，点击「新建」创建
            </div>
          )}
        </div>
      </div>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="py-4 px-6 border-b border-[#334155] flex items-center justify-between gap-4">
          <span className="text-[1rem] text-[#F8FAFC] font-semibold whitespace-nowrap overflow-hidden text-ellipsis">{activeBase ? activeBase.name : '请选择知识库'}</span>
          <div className="flex gap-2 items-center">
            <input
              className="py-[0.4rem] px-[0.7rem] bg-[rgba(0,0,0,0.3)] border border-[#334155] rounded-[6px] text-[#e0e0e0] text-[0.9375rem] w-[200px] outline-none focus:border-[rgba(45,212,191,0.15)]"
              placeholder="搜索知识库..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
            />
            <button className={actionBtnBase} onClick={handleSearch} disabled={searching}>
              {searching ? '搜索中...' : '🔍'}
            </button>
            {activeBaseId && (
              <>
                <button className={actionBtnBase} onClick={openSettings} title="模型配置">⚙️</button>
                <label className={cn(actionBtnBase, actionBtnPrimary)} style={{ cursor: uploading ? 'not-allowed' : 'pointer' }}>
                  {uploading ? '上传中...' : '📤 上传文件'}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".md,.txt,.markdown,.rst,.tex,.json,.csv,.pdf,.docx,.doc"
                    multiple
                    onChange={handleFileUpload}
                    style={{ display: 'none' }}
                    disabled={uploading}
                  />
                </label>
                <button className={actionBtnBase} onClick={() => setShowAddNote(true)}>📝 添加笔记</button>
              </>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-0 px-6 border-b border-[#334155]">
          {TABS.map(tab => (
            <button
              key={tab.key}
              className={cn(
                'py-[0.6rem] px-4 bg-transparent border-none border-b-2 border-b-transparent text-[#94A3B8] text-[0.9375rem] cursor-pointer font-medium transition-all duration-150 hover:text-[#CBD5E1]',
                activeTab === tab.key && 'text-[#3498db] border-b-[#3498db]'
              )}
              onClick={() => { setActiveTab(tab.key); setShowSearch(false); }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 px-6">
          {msg && (
            <div className={cn('py-2 px-4 rounded-[8px] text-[0.9375rem] text-center mb-4', msg.includes('失败') || msg.startsWith('✗') ? 'text-[#e74c3c] bg-[rgba(248,113,113,0.15)]' : 'text-[#2ecc71] bg-[rgba(74,222,128,0.15)]')}>
              {msg}
            </div>
          )}

          {showSearch && (
            <div className="mt-[0.8rem]">
              <div className="flex justify-between items-center mb-2">
                <span style={{ color: '#aaa', fontSize: '0.85rem' }}>搜索结果: {searchResults.length} 条</span>
                <button className={actionBtnBase} onClick={() => { setShowSearch(false); setSearchResults([]); setSelectedResult(null); }}>关闭</button>
              </div>
              {searchResults.map(r => (
                <div
                  key={r.id}
                  onClick={() => setSelectedResult(selectedResult?.id === r.id ? null : r)}
                  className="py-[0.7rem] px-[0.7rem] bg-[rgba(0,0,0,0.15)] border border-[#334155] rounded-[8px] mb-2 cursor-pointer hover:border-[#3498db] transition-colors"
                >
                  <div className="flex justify-between mb-[0.3rem]">
                    <span className="text-[#F8FAFC] font-semibold text-[0.88rem]">{r.title}</span>
                    <div className="flex items-center gap-2">
                      {r.metadata?.domain && (
                        <span className="text-[0.7rem] px-[0.4rem] py-[0.1rem] rounded bg-[rgba(52,152,219,0.15)] text-[#3498db]">{r.metadata.domain}</span>
                      )}
                      {r.metadata?.year && (
                        <span className="text-[0.7rem] px-[0.4rem] py-[0.1rem] rounded bg-[rgba(46,204,113,0.15)] text-[#2ecc71]">{r.metadata.year}</span>
                      )}
                      <span className="text-[#3498db] text-[0.875rem]">{(r.score * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                  <div className="text-[#94A3B8] text-[0.82rem] whitespace-pre-wrap leading-[1.4]">{r.content.slice(0, 300)}{r.content.length > 300 ? '...' : ''}</div>
                  {r.source && <div style={{ color: '#666', fontSize: '0.75rem', marginTop: '0.2rem' }}>来源: {r.source}</div>}
                </div>
              ))}
              {searchResults.length === 0 && <div className="text-[#64748B] text-center p-[3rem_1rem] text-[0.9375rem]">无匹配结果</div>}
            </div>
          )}

          {/* 搜索结果详情弹窗 */}
          {selectedResult && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setSelectedResult(null)}>
              <div className="bg-[#1E293B] border border-[#334155] rounded-[12px] w-[720px] max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="flex justify-between items-center px-5 py-4 border-b border-[#334155]">
                  <div className="flex-1 min-w-0">
                    <div className="text-[#F8FAFC] font-semibold text-[1rem] truncate">{selectedResult.title}</div>
                    <div className="flex items-center gap-2 mt-1">
                      {selectedResult.metadata?.domain && (
                        <span className="text-[0.72rem] px-2 py-0.5 rounded bg-[rgba(52,152,219,0.15)] text-[#3498db]">{selectedResult.metadata.domain}</span>
                      )}
                      {selectedResult.metadata?.year && (
                        <span className="text-[0.72rem] px-2 py-0.5 rounded bg-[rgba(46,204,113,0.15)] text-[#2ecc71]">{selectedResult.metadata.year}</span>
                      )}
                      {selectedResult.metadata?.method && (
                        <span className="text-[0.72rem] px-2 py-0.5 rounded bg-[rgba(155,89,182,0.15)] text-[#9b59b6]">{selectedResult.metadata.method}</span>
                      )}
                      <span className="text-[0.72rem] text-[#64748B]">相关度: {(selectedResult.score * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                  <button onClick={() => setSelectedResult(null)} className="ml-3 text-[#64748B] hover:text-[#F8FAFC] text-xl leading-none p-1">×</button>
                </div>
                <div className="flex-1 overflow-y-auto p-5">
                  <div className="text-[#CBD5E1] text-[0.88rem] whitespace-pre-wrap leading-[1.6] leading-relaxed">
                    {selectedResult.content}
                  </div>
                </div>
                <div className="px-5 py-3 border-t border-[#334155] flex justify-between items-center">
                  <div className="text-[0.75rem] text-[#64748B]">
                    {selectedResult.metadata?.title && <span>标题: {selectedResult.metadata.title}</span>}
                    {selectedResult.source && <span className="ml-3">来源: {selectedResult.source}</span>}
                  </div>
                  <button
                    className="px-4 py-1.5 bg-[#2563eb] text-white text-[0.82rem] rounded-md hover:bg-[#1d4ed8] transition-colors"
                    onClick={() => {
                      navigator.clipboard.writeText(selectedResult.content);
                      showMsg('内容已复制到剪贴板');
                    }}
                  >
                    复制内容
                  </button>
                </div>
              </div>
            </div>
          )}

          {!showSearch && (
            <>
              {filteredItems.length > 0 && (
                <div className="flex items-center gap-2 mb-[0.8rem]">
                  <input
                    type="checkbox"
                    checked={selectedItemIds.size > 0 && selectedItemIds.size === filteredItems.length}
                    onChange={e => { e.target.checked ? selectAllItems() : clearSelection(); }}
                    style={{ cursor: 'pointer' }}
                  />
                  <span style={{ color: '#888', fontSize: '0.8rem' }}>全选 ({selectedItemIds.size}/{filteredItems.length})</span>
                  {selectedItemIds.size > 0 && (
                    <>
                      <button
                        className={cn(actionBtnBase, actionBtnPrimary)}
                        onClick={handleDownloadSelectedItems}
                        style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem' }}
                      >
                        📥 批量下载 ({selectedItemIds.size})
                      </button>
                      <button
                        className={cn(actionBtnBase, actionBtnPrimary)}
                        onClick={handleDeleteSelectedItems}
                        style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem' }}
                      >
                        🗑️ 批量删除 ({selectedItemIds.size})
                      </button>
                    </>
                  )}
                </div>
              )}
              {filteredItems.length === 0 && (
                <div className="text-[#64748B] text-center p-[3rem_1rem] text-[0.9375rem]">
                  该分类下暂无条目
                  {activeTab === 'file' && <div style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>点击「上传文件」添加</div>}
                  {activeTab === 'note' && <div style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>点击「添加笔记」添加</div>}
                </div>
              )}
              {filteredItems.map(item => {
                const name = isFileMeta(item.content) ? item.content.name : (item.content as string).slice(0, 60);
                const size = isFileMeta(item.content) ? item.content.size : undefined;
                const isSelected = selectedItemIds.has(item.id);
                return (
                  <div key={item.id} className="flex items-center gap-[0.8rem] py-[0.7rem] px-[0.9rem] bg-[rgba(0,0,0,0.15)] border border-[#334155] rounded-[8px] mb-2 transition-[background] duration-150 hover:bg-[rgba(0,0,0,0.25)]" style={{ background: isSelected ? 'rgba(52,152,219,0.08)' : undefined }}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelectItem(item.id)}
                      style={{ cursor: 'pointer', marginRight: '0.4rem' }}
                    />
                    <span className="text-[1.1rem] w-[1.5rem] text-center shrink-0">{typeIcon(item.type)}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-[#E2E8F0] text-[0.88rem] font-medium whitespace-nowrap overflow-hidden text-ellipsis">{name}</div>
                      {item.source && <div className="text-[#64748B] text-[0.875rem] mt-[0.15rem]">{item.source}</div>}
                    </div>
                    <div className="flex items-center gap-[0.6rem] shrink-0">
                      {size !== undefined && <span className="text-[#94A3B8] text-[0.78rem]">{formatBytes(size)}</span>}
                      {item.type === 'file' && <span className="text-[0.9375rem]" title={item.processingStatus}>{statusIcon(item.processingStatus)}</span>}
                      {item.type === 'file' && isFileMeta(item.content) && (
                        <button className="py-[0.2rem] px-[0.4rem] bg-[rgba(45,212,191,0.15)] border border-[rgba(45,212,191,0.15)] rounded-[4px] text-[#3498db] text-[0.875rem] cursor-pointer opacity-0 transition-[opacity] duration-150 hover:opacity-100" onClick={() => handleDownloadItem(item)} title="下载">📥</button>
                      )}
                      {item.type === 'file' && isFileMeta(item.content) && (
                        <button className="py-[0.2rem] px-[0.4rem] bg-[rgba(155,89,182,0.1)] border border-[rgba(155,89,182,0.2)] rounded-[4px] text-[#9b59b6] text-[0.875rem] cursor-pointer opacity-0 transition-[opacity] duration-150 hover:opacity-100" onClick={() => triggerReplaceFile(item)} title="替换文件">🔄</button>
                      )}
                      {item.type === 'note' && (
                        <button className="py-[0.2rem] px-[0.4rem] bg-[rgba(243,156,18,0.1)] border border-[rgba(243,156,18,0.2)] rounded-[4px] text-[#f39c12] text-[0.875rem] cursor-pointer opacity-0 transition-[opacity] duration-150 hover:opacity-100" onClick={() => openEditNote(item)} title="编辑">✏️</button>
                      )}
                      <button className="py-[0.2rem] px-[0.4rem] bg-[rgba(248,113,113,0.15)] border border-[rgba(248,113,113,0.15)] rounded-[4px] text-[#e74c3c] text-[0.875rem] cursor-pointer opacity-0 transition-[opacity] duration-150 hover:opacity-100" onClick={() => handleDeleteItem(item.id)}>删除</button>
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      </div>

      {/* Create Base Modal */}
      {showCreateBase && (
        <div className="fixed inset-0 bg-[rgba(0,0,0,0.6)] flex items-center justify-center z-[1000]" onClick={() => setShowCreateBase(false)}>
          <div className="bg-[#1e1e2e] border border-[#334155] rounded-[14px] p-6 w-[90%] max-w-[500px] flex flex-col gap-4" onClick={e => e.stopPropagation()}>
            <div className="text-[1rem] text-[#F8FAFC] font-semibold">新建知识库</div>
            <input
              className={modalInputBase}
              placeholder="知识库名称"
              value={newBaseName}
              onChange={e => setNewBaseName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreateBase()}
              autoFocus
            />
            <div className="flex gap-2 mt-[0.6rem]">
              <button
                className={cn(actionBtnBase, newBaseScope === 'global' && actionBtnPrimary)}
                onClick={() => setNewBaseScope('global')}
                type="button"
              >
                🌐 全局公共
              </button>
              <button
                className={cn(actionBtnBase, newBaseScope === 'project' && actionBtnPrimary)}
                onClick={() => setNewBaseScope('project')}
                type="button"
              >
                📁 项目私有
              </button>
            </div>
            {newBaseScope === 'project' && (
              <input
                className={modalInputBase}
                placeholder="项目名（如 work_2026_xxx）"
                value={newBaseProjectName}
                onChange={e => setNewBaseProjectName(e.target.value)}
                style={{ marginTop: '0.5rem' }}
              />
            )}
            <div className="flex justify-end gap-2">
              <button className={actionBtnBase} onClick={() => setShowCreateBase(false)}>取消</button>
              <button className={cn(actionBtnBase, actionBtnPrimary)} onClick={handleCreateBase}>创建</button>
            </div>
          </div>
        </div>
      )}

      {/* Rename Base Modal */}
      {showRenameBase && (
        <div className="fixed inset-0 bg-[rgba(0,0,0,0.6)] flex items-center justify-center z-[1000]" onClick={() => setShowRenameBase(false)}>
          <div className="bg-[#1e1e2e] border border-[#334155] rounded-[14px] p-6 w-[90%] max-w-[500px] flex flex-col gap-4" onClick={e => e.stopPropagation()}>
            <div className="text-[1rem] text-[#F8FAFC] font-semibold">重命名知识库</div>
            <input
              className={modalInputBase}
              placeholder="新名称"
              value={renameBaseName}
              onChange={e => setRenameBaseName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleRenameBase()}
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button className={actionBtnBase} onClick={() => setShowRenameBase(false)}>取消</button>
              <button className={cn(actionBtnBase, actionBtnPrimary)} onClick={handleRenameBase}>确认</button>
            </div>
          </div>
        </div>
      )}

      {/* Add / Edit Note Modal */}
      {showAddNote && (
        <div className="fixed inset-0 bg-[rgba(0,0,0,0.6)] flex items-center justify-center z-[1000]" onClick={closeAddNoteModal}>
          <div className="bg-[#1e1e2e] border border-[#334155] rounded-[14px] p-6 w-[90%] max-w-[500px] flex flex-col gap-4" onClick={e => e.stopPropagation()}>
            <div className="text-[1rem] text-[#F8FAFC] font-semibold">{editingItem ? '编辑笔记' : '添加笔记'}</div>
            <textarea
              className="py-[0.6rem] px-[0.6rem] bg-[rgba(0,0,0,0.3)] border border-[#334155] rounded-[8px] text-[#e0e0e0] text-[0.9375rem] outline-none w-full min-h-[120px] resize-y font-[inherit] focus:border-[rgba(45,212,191,0.15)]"
              placeholder="输入笔记内容..."
              value={noteContent}
              onChange={e => setNoteContent(e.target.value)}
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button className={actionBtnBase} onClick={closeAddNoteModal}>取消</button>
              <button className={cn(actionBtnBase, actionBtnPrimary)} onClick={handleAddNote}>
                {editingItem ? '保存' : '添加'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Replace File Input */}
      <input
        ref={replaceFileInputRef}
        type="file"
        accept=".md,.txt,.markdown,.rst,.tex,.json,.csv,.pdf,.docx,.doc"
        style={{ display: 'none' }}
        onChange={handleReplaceFile}
      />

      {/* Settings Modal */}
      {showSettings && (
        <div className="fixed inset-0 bg-[rgba(0,0,0,0.6)] flex items-center justify-center z-[1000]" onClick={() => setShowSettings(false)}>
          <div className="bg-[#1e1e2e] border border-[#334155] rounded-[14px] p-6 w-[90%] max-w-[500px] flex flex-col gap-4" style={{ maxHeight: '80vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
            <div className="text-[1rem] text-[#F8FAFC] font-semibold">模型配置</div>
            <div className="flex flex-col gap-[0.8rem]">
              <div>
                <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '0.3rem' }}>嵌入模型</div>
                <select
                  className={modalInputBase}
                  value={settingsEmbedding}
                  onChange={e => setSettingsEmbedding(e.target.value)}
                >
                  <option value="tfidf">TF-IDF（本地，无依赖）</option>
                  <option value="sentence-transformers">Sentence Transformers（本地）</option>
                  <option value="openai">OpenAI / SiliconFlow / 兼容 API</option>
                  <option value="ollama">Ollama（本地服务）</option>
                  <option value="voyageai">VoyageAI API</option>
                </select>
                {settingsEmbedding !== 'tfidf' && (
                  <input
                    className={modalInputBase}
                    style={{ marginTop: '0.4rem' }}
                    placeholder={
                      settingsEmbedding === 'sentence-transformers' ? '模型名称 (默认: all-MiniLM-L6-v2)' :
                      settingsEmbedding === 'openai' ? '模型名称 (默认: text-embedding-3-small)' :
                      settingsEmbedding === 'ollama' ? '模型名称 (默认: nomic-embed-text)' :
                      settingsEmbedding === 'voyageai' ? '模型名称 (默认: voyage-3)' : '模型名称'
                    }
                    value={settingsEmbeddingModel}
                    onChange={e => setSettingsEmbeddingModel(e.target.value)}
                  />
                )}
                {(settingsEmbedding === 'openai' || settingsEmbedding === 'voyageai') && (
                  <input
                    className={modalInputBase}
                    style={{ marginTop: '0.4rem' }}
                    type="password"
                    placeholder="API Key"
                    value={settingsEmbeddingApiKey}
                    onChange={e => setSettingsEmbeddingApiKey(e.target.value)}
                  />
                )}
                {(settingsEmbedding === 'openai' || settingsEmbedding === 'ollama') && (
                  <input
                    className={modalInputBase}
                    style={{ marginTop: '0.4rem' }}
                    placeholder={
                      settingsEmbedding === 'openai' ? 'Base URL (可选，默认: https://api.openai.com/v1)' :
                      'Base URL (可选，默认: http://localhost:11434)'
                    }
                    value={settingsEmbeddingBaseUrl}
                    onChange={e => setSettingsEmbeddingBaseUrl(e.target.value)}
                  />
                )}
              </div>
              <div>
                <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '0.3rem' }}>重排模型</div>
                <select
                  className={modalInputBase}
                  value={settingsReranker}
                  onChange={e => setSettingsReranker(e.target.value)}
                >
                  <option value="none">不使用重排</option>
                  <option value="cross-encoder">Cross Encoder（本地）</option>
                  <option value="tfidf">TF-IDF（本地）</option>
                  <option value="voyageai">VoyageAI API</option>
                  <option value="bailian">百炼 (Bailian) API</option>
                  <option value="jina">Jina AI API</option>
                  <option value="tei">TEI (HuggingFace) 本地服务</option>
                </select>
                {settingsReranker !== 'none' && settingsReranker !== 'tfidf' && settingsReranker !== 'tei' && (
                  <input
                    className={modalInputBase}
                    style={{ marginTop: '0.4rem' }}
                    placeholder={
                      settingsReranker === 'cross-encoder' ? '模型名称 (默认: cross-encoder/ms-marco-MiniLM-L-6-v2)' :
                      settingsReranker === 'voyageai' ? '模型名称 (默认: rerank-2)' :
                      settingsReranker === 'bailian' ? '模型名称 (默认: gte-rerank)' :
                      settingsReranker === 'jina' ? '模型名称 (默认: jina-reranker-v2-base-multilingual)' : '模型名称'
                    }
                    value={settingsRerankerModel}
                    onChange={e => setSettingsRerankerModel(e.target.value)}
                  />
                )}
                {(settingsReranker === 'voyageai' || settingsReranker === 'bailian' || settingsReranker === 'jina') && (
                  <input
                    className={modalInputBase}
                    style={{ marginTop: '0.4rem' }}
                    type="password"
                    placeholder="API Key"
                    value={settingsRerankerApiKey}
                    onChange={e => setSettingsRerankerApiKey(e.target.value)}
                  />
                )}
                {settingsReranker === 'tei' && (
                  <input
                    className={modalInputBase}
                    style={{ marginTop: '0.4rem' }}
                    placeholder="Base URL (可选，默认: http://localhost:8080)"
                    value={settingsRerankerBaseUrl}
                    onChange={e => setSettingsRerankerBaseUrl(e.target.value)}
                  />
                )}
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button className={actionBtnBase} onClick={() => setShowSettings(false)}>取消</button>
              <button className={cn(actionBtnBase, actionBtnPrimary)} onClick={saveSettings}>保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
