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
        // 显式重新拉取列表，避免本地追加的对象与后端返回字段不一致
        // （新建返回 items:[], 列表接口返回 item_count, 字段不同步会导致后续操作异常）
        await loadBases();
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

  const actionBtnBase = "inline-flex items-center gap-1.5 min-h-[34px] px-3.5 py-2 bg-muted border border-border rounded-lg text-muted-foreground text-sm cursor-pointer transition-colors duration-150 whitespace-nowrap hover:bg-accent hover:text-foreground";
  const actionBtnPrimary = "bg-primary text-primary-foreground border-primary hover:bg-primary hover:text-primary-foreground hover:opacity-90";
  const modalInputBase = "h-10 px-3.5 bg-muted border border-border rounded-lg text-foreground text-sm outline-none w-full focus:border-primary focus:ring-2 focus:ring-primary/20 placeholder:text-muted-foreground";

  return (
    <div className="flex h-full min-h-[500px] bg-card border border-border rounded-xl shadow-sm overflow-hidden">
      {/* Sidebar */}
      <div className="w-72 shrink-0 flex flex-col border-r border-border bg-muted/50">
        <div className="flex items-center justify-between px-5 h-14 border-b border-border shrink-0">
          <span className="text-lg text-foreground font-semibold">📚 知识库</span>
          <button className="inline-flex items-center justify-center min-h-[34px] px-3.5 py-2 bg-primary border border-primary rounded-lg text-primary-foreground text-sm cursor-pointer font-semibold transition-opacity hover:opacity-90" onClick={() => setShowCreateBase(true)}>+ 新建</button>
        </div>
        <div className="flex items-center gap-1 h-11 px-5 border-b border-border shrink-0">
          {(['all', 'global', 'project'] as const).map(s => (
            <button
              key={s}
              className={cn(actionBtnBase, scopeFilter === s && actionBtnPrimary)}
              onClick={() => setScopeFilter(s)}
              type="button"
            >
              {s === 'all' ? '全部' : s === 'global' ? '🌐 全局' : '📁 项目'}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto p-2.5">
          {bases.map(base => (
            <div
              key={base.id}
              className={cn('flex items-center justify-between py-3 px-3.5 rounded-lg cursor-pointer mb-1.5 transition-colors duration-150 border border-transparent hover:bg-accent', base.id === activeBaseId && 'bg-primary/10 border-primary/30')}
              onClick={() => { setActiveBaseId(base.id); setShowSearch(false); setSearchResults([]); }}
            >
              <div className="flex flex-col flex-1 min-w-0">
                <span className={cn('text-muted-foreground text-sm font-medium whitespace-nowrap overflow-hidden text-ellipsis', base.id === activeBaseId && 'text-foreground')}>{base.name}</span>
                <span className="text-xs text-primary mt-1">
                  {base.scope === 'project'
                    ? `📁 ${base.project_name || '项目'}`
                    : '🌐 全局'}
                </span>
              </div>
              <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-lg ml-2">{base.item_count ?? 0}</span>
              <button
                className="opacity-0 transition-opacity duration-150 ml-1 py-0.5 px-1 bg-transparent border-none text-muted-foreground cursor-pointer text-sm hover:opacity-100"
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
            <div className="flex-1 flex items-center justify-center text-center text-sm text-muted-foreground px-4 py-8">
              暂无知识库，点击「新建」创建
            </div>
          )}
        </div>
      </div>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0 bg-card">
        {/* Header */}
        <div className="flex items-center justify-between px-5 h-14 border-b border-border shrink-0 gap-4">
          <span className="text-base text-foreground font-semibold whitespace-nowrap overflow-hidden text-ellipsis">{activeBase ? activeBase.name : '请选择知识库'}</span>
          <div className="flex gap-2 items-center shrink-0">
            <input
              className="h-10 px-3.5 bg-muted border border-border rounded-lg text-foreground text-sm w-[240px] outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 placeholder:text-muted-foreground"
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
                <label className={cn(actionBtnBase, actionBtnPrimary, uploading && 'cursor-not-allowed')}>
                  {uploading ? '上传中...' : '📤 上传文件'}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".md,.txt,.markdown,.rst,.tex,.json,.csv,.pdf,.docx,.doc"
                    multiple
                    onChange={handleFileUpload}
                    className="hidden"
                    disabled={uploading}
                  />
                </label>
                <button className={actionBtnBase} onClick={() => setShowAddNote(true)}>📝 添加笔记</button>
              </>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 h-11 px-5 border-b border-border shrink-0">
          {TABS.map(tab => (
            <button
              key={tab.key}
              className={cn(
                'inline-flex items-center px-3 h-full bg-transparent border-none border-b-2 border-b-transparent text-muted-foreground text-sm cursor-pointer font-medium transition-colors duration-150 hover:text-foreground',
                activeTab === tab.key && 'text-primary border-b-primary'
              )}
              onClick={() => { setActiveTab(tab.key); setShowSearch(false); }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {msg && (
            <div className={cn('py-2 px-4 rounded-md text-sm text-center mb-4', msg.includes('失败') || msg.startsWith('✗') ? 'text-error bg-error/10' : 'text-success bg-success/10')}>
              {msg}
            </div>
          )}

          {showSearch && (
            <div className="mt-3">
              <div className="flex justify-between items-center mb-2">
                <span className="text-muted-foreground text-sm">搜索结果: {searchResults.length} 条</span>
                <button className={actionBtnBase} onClick={() => { setShowSearch(false); setSearchResults([]); setSelectedResult(null); }}>关闭</button>
              </div>
              {searchResults.map(r => (
                <div
                  key={r.id}
                  onClick={() => setSelectedResult(selectedResult?.id === r.id ? null : r)}
                  className="py-3 px-3 bg-muted border border-border rounded-md mb-2 cursor-pointer hover:border-primary transition-colors"
                >
                  <div className="flex justify-between mb-1.5">
                    <span className="text-foreground font-semibold text-sm">{r.title}</span>
                    <div className="flex items-center gap-2">
                      {r.metadata?.domain && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary">{r.metadata.domain}</span>
                      )}
                      {r.metadata?.year && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-success/10 text-success">{r.metadata.year}</span>
                      )}
                      <span className="text-primary text-sm">{(r.score * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                  <div className="text-muted-foreground text-sm whitespace-pre-wrap leading-[1.4]">{r.content.slice(0, 300)}{r.content.length > 300 ? '...' : ''}</div>
                  {r.source && <div className="text-muted-foreground text-xs mt-0.5">来源: {r.source}</div>}
                </div>
              ))}
              {searchResults.length === 0 && <div className="text-muted-foreground text-center py-12 px-4 text-sm">无匹配结果</div>}
            </div>
          )}

          {/* 搜索结果详情弹窗 */}
          {selectedResult && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setSelectedResult(null)}>
              <div className="bg-card border border-border rounded-xl w-[720px] max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="flex justify-between items-center px-5 py-4 border-b border-border">
                  <div className="flex-1 min-w-0">
                    <div className="text-foreground font-semibold text-base truncate">{selectedResult.title}</div>
                    <div className="flex items-center gap-2 mt-1">
                      {selectedResult.metadata?.domain && (
                        <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">{selectedResult.metadata.domain}</span>
                      )}
                      {selectedResult.metadata?.year && (
                        <span className="text-xs px-2 py-0.5 rounded bg-success/10 text-success">{selectedResult.metadata.year}</span>
                      )}
                      {selectedResult.metadata?.method && (
                        <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">{selectedResult.metadata.method}</span>
                      )}
                      <span className="text-xs text-muted-foreground">相关度: {(selectedResult.score * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                  <button onClick={() => setSelectedResult(null)} className="ml-3 text-muted-foreground hover:text-foreground text-xl leading-none p-1">×</button>
                </div>
                <div className="flex-1 overflow-y-auto p-5">
                  <div className="text-foreground text-sm whitespace-pre-wrap leading-relaxed">
                    {selectedResult.content}
                  </div>
                </div>
                <div className="px-5 py-3 border-t border-border flex justify-between items-center">
                  <div className="text-xs text-muted-foreground">
                    {selectedResult.metadata?.title && <span>标题: {selectedResult.metadata.title}</span>}
                    {selectedResult.source && <span className="ml-3">来源: {selectedResult.source}</span>}
                  </div>
                  <button
                    className="px-4 py-1.5 bg-primary text-primary-foreground text-sm rounded-md transition-opacity hover:opacity-90"
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
                <div className="flex items-center gap-2 mb-3">
                  <input
                    type="checkbox"
                    checked={selectedItemIds.size > 0 && selectedItemIds.size === filteredItems.length}
                    onChange={e => { e.target.checked ? selectAllItems() : clearSelection(); }}
                    className="cursor-pointer"
                  />
                  <span className="text-muted-foreground text-sm">全选 ({selectedItemIds.size}/{filteredItems.length})</span>
                  {selectedItemIds.size > 0 && (
                    <>
                      <button
                        className={cn(actionBtnBase, actionBtnPrimary, 'py-1 px-2.5')}
                        onClick={handleDownloadSelectedItems}
                      >
                        📥 批量下载 ({selectedItemIds.size})
                      </button>
                      <button
                        className="py-1 px-2.5 bg-error/10 border border-error/20 rounded-md text-error text-xs cursor-pointer transition-colors duration-150 whitespace-nowrap hover:bg-error/15"
                        onClick={handleDeleteSelectedItems}
                      >
                        🗑️ 批量删除 ({selectedItemIds.size})
                      </button>
                    </>
                  )}
                </div>
              )}
              {filteredItems.length === 0 && (
                <div className="flex-1 flex flex-col items-center justify-center text-center text-muted-foreground px-4 py-8 text-sm" style={{ minHeight: '60%' }}>
                  该分类下暂无条目
                  {activeTab === 'file' && <div className="mt-2 text-sm">点击「上传文件」添加</div>}
                  {activeTab === 'note' && <div className="mt-2 text-sm">点击「添加笔记」添加</div>}
                </div>
              )}
              {filteredItems.map(item => {
                const name = isFileMeta(item.content) ? item.content.name : (item.content as string).slice(0, 60);
                const size = isFileMeta(item.content) ? item.content.size : undefined;
                const isSelected = selectedItemIds.has(item.id);
                return (
                  <div key={item.id} className={cn('flex items-center gap-3 py-3 px-3.5 bg-muted border border-border rounded-md mb-2 transition-colors duration-150 hover:bg-foreground/5', isSelected && 'bg-primary/10')}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelectItem(item.id)}
                      className="cursor-pointer mr-1.5"
                    />
                    <span className="text-lg w-[1.5rem] text-center shrink-0">{typeIcon(item.type)}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-foreground text-sm font-medium whitespace-nowrap overflow-hidden text-ellipsis">{name}</div>
                      {item.source && <div className="text-muted-foreground text-sm mt-0.5">{item.source}</div>}
                    </div>
                    <div className="flex items-center gap-2.5 shrink-0">
                      {size !== undefined && <span className="text-muted-foreground text-xs">{formatBytes(size)}</span>}
                      {item.type === 'file' && <span className="text-sm" title={item.processingStatus}>{statusIcon(item.processingStatus)}</span>}
                      {item.type === 'file' && isFileMeta(item.content) && (
                        <button className="py-0.5 px-1.5 bg-primary/10 border border-primary/20 rounded text-primary text-sm cursor-pointer opacity-0 transition-opacity duration-150 hover:opacity-100" onClick={() => handleDownloadItem(item)} title="下载">📥</button>
                      )}
                      {item.type === 'file' && isFileMeta(item.content) && (
                        <button className="py-0.5 px-1.5 bg-primary/10 border border-primary/20 rounded text-primary text-sm cursor-pointer opacity-0 transition-opacity duration-150 hover:opacity-100" onClick={() => triggerReplaceFile(item)} title="替换文件">🔄</button>
                      )}
                      {item.type === 'note' && (
                        <button className="py-0.5 px-1.5 bg-warning/10 border border-warning/20 rounded text-warning text-sm cursor-pointer opacity-0 transition-opacity duration-150 hover:opacity-100" onClick={() => openEditNote(item)} title="编辑">✏️</button>
                      )}
                      <button className="py-0.5 px-1.5 bg-error/10 border border-error/20 rounded text-error text-sm cursor-pointer opacity-0 transition-opacity duration-150 hover:opacity-100" onClick={() => handleDeleteItem(item.id)}>删除</button>
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
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[1000] p-4" onClick={() => setShowCreateBase(false)}>
          <div className="bg-card border border-border rounded-xl p-8 w-full max-w-[560px] flex flex-col gap-5" onClick={e => e.stopPropagation()}>
            <div className="text-lg text-foreground font-semibold">新建知识库</div>
            <input
              className={modalInputBase}
              placeholder="知识库名称"
              value={newBaseName}
              onChange={e => setNewBaseName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreateBase()}
              autoFocus
            />
            <div className="flex gap-3">
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
              />
            )}
            <div className="flex justify-end gap-2 mt-2">
              <button className={actionBtnBase} onClick={() => setShowCreateBase(false)}>取消</button>
              <button className={cn(actionBtnBase, actionBtnPrimary)} onClick={handleCreateBase}>创建</button>
            </div>
          </div>
        </div>
      )}

      {/* Rename Base Modal */}
      {showRenameBase && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[1000]" onClick={() => setShowRenameBase(false)}>
          <div className="bg-card border border-border rounded-xl p-6 w-[90%] max-w-[500px] flex flex-col gap-4" onClick={e => e.stopPropagation()}>
            <div className="text-base text-foreground font-semibold">重命名知识库</div>
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
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[1000]" onClick={closeAddNoteModal}>
          <div className="bg-card border border-border rounded-xl p-6 w-[90%] max-w-[500px] flex flex-col gap-4" onClick={e => e.stopPropagation()}>
            <div className="text-base text-foreground font-semibold">{editingItem ? '编辑笔记' : '添加笔记'}</div>
            <textarea
              className={cn(modalInputBase, 'min-h-[180px] resize-y leading-relaxed')}
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
        className="hidden"
        onChange={handleReplaceFile}
      />

      {/* Settings Modal */}
      {showSettings && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[1000]" onClick={() => setShowSettings(false)}>
          <div className="bg-card border border-border rounded-xl p-6 w-[90%] max-w-[500px] flex flex-col gap-4 max-h-[80vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="text-base text-foreground font-semibold">模型配置</div>
            <div className="flex flex-col gap-3">
              <div>
                <div className="text-muted-foreground text-sm mb-1.5">嵌入模型</div>
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
                    className={cn(modalInputBase, 'mt-1.5')}
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
                    className={cn(modalInputBase, 'mt-1.5')}
                    type="password"
                    placeholder="API Key"
                    value={settingsEmbeddingApiKey}
                    onChange={e => setSettingsEmbeddingApiKey(e.target.value)}
                  />
                )}
                {(settingsEmbedding === 'openai' || settingsEmbedding === 'ollama') && (
                  <input
                    className={cn(modalInputBase, 'mt-1.5')}
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
                <div className="text-muted-foreground text-sm mb-1.5">重排模型</div>
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
                    className={cn(modalInputBase, 'mt-1.5')}
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
                    className={cn(modalInputBase, 'mt-1.5')}
                    type="password"
                    placeholder="API Key"
                    value={settingsRerankerApiKey}
                    onChange={e => setSettingsRerankerApiKey(e.target.value)}
                  />
                )}
                {settingsReranker === 'tei' && (
                  <input
                    className={cn(modalInputBase, 'mt-1.5')}
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
