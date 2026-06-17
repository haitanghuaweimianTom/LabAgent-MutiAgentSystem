'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import styles from './KnowledgeBaseManager.module.css';

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

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
}

interface SearchResult {
  id: string;
  title: string;
  content: string;
  source?: string;
  score: number;
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

  // Create base modal
  const [showCreateBase, setShowCreateBase] = useState(false);
  const [newBaseName, setNewBaseName] = useState('');

  // Rename base modal
  const [showRenameBase, setShowRenameBase] = useState(false);
  const [renameBaseName, setRenameBaseName] = useState('');

  // Upload
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Add note modal
  const [showAddNote, setShowAddNote] = useState(false);
  const [noteContent, setNoteContent] = useState('');

  // Search
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [showSearch, setShowSearch] = useState(false);

  // Multi-select
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(new Set());

  // Settings modal
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
      const res = await fetch(apiBase() + '/knowledge/bases');
      if (res.ok) {
        const data = await res.json();
        const list: KnowledgeBase[] = data.bases || [];
        setBases(list);
        if (list.length > 0 && !activeBaseId) {
          setActiveBaseId(list[0].id);
        }
      }
    } catch {
      showMsg('加载知识库列表失败', true);
    }
  }, [activeBaseId, showMsg]);

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
    try {
      const res = await fetch(apiBase() + '/knowledge/bases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (data.success && data.base) {
        showMsg(`知识库 "${name}" 已创建`);
        setShowCreateBase(false);
        setNewBaseName('');
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
    try {
      const res = await fetch(apiBase() + `/knowledge/bases/${activeBaseId}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'note', content }),
      });
      const data = await res.json();
      if (data.success) {
        showMsg('笔记已添加');
        setShowAddNote(false);
        setNoteContent('');
        loadItems(activeBaseId);
        loadBases();
      } else {
        showMsg(data.detail || '添加失败', true);
      }
    } catch {
      showMsg('添加失败', true);
    }
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
        // 稍微延迟，避免浏览器阻塞连续下载
        await new Promise(r => setTimeout(r, 150));
      } catch { /* ignore single failure */ }
    }
    showMsg(`已下载 ${successCount} 个文件`);
    setSelectedItemIds(new Set());
  };

  return (
    <div className={styles.container}>
      {/* Sidebar */}
      <div className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <span className={styles.sidebarTitle}>📚 知识库</span>
          <button className={styles.addBaseBtn} onClick={() => setShowCreateBase(true)}>+ 新建</button>
        </div>
        <div className={styles.baseList}>
          {bases.map(base => (
            <div
              key={base.id}
              className={`${styles.baseItem} ${base.id === activeBaseId ? styles.baseItemActive : ''}`}
              onClick={() => { setActiveBaseId(base.id); setShowSearch(false); setSearchResults([]); }}
            >
              <span className={styles.baseItemName}>{base.name}</span>
              <span className={styles.baseItemCount}>{base.item_count ?? 0}</span>
              <button
                className={styles.baseItemMenu}
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
      <div className={styles.main}>
        {/* Header */}
        <div className={styles.mainHeader}>
          <span className={styles.mainTitle}>{activeBase ? activeBase.name : '请选择知识库'}</span>
          <div className={styles.headerActions}>
            <input
              className={styles.searchInput}
              placeholder="搜索知识库..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
            />
            <button className={styles.actionBtn} onClick={handleSearch} disabled={searching}>
              {searching ? '搜索中...' : '🔍'}
            </button>
            {activeBaseId && (
              <>
                <button className={styles.actionBtn} onClick={openSettings} title="模型配置">⚙️</button>
                <label className={`${styles.actionBtn} ${styles.actionBtnPrimary}`} style={{ cursor: uploading ? 'not-allowed' : 'pointer' }}>
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
                <button className={styles.actionBtn} onClick={() => setShowAddNote(true)}>📝 添加笔记</button>
              </>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className={styles.tabs}>
          {TABS.map(tab => (
            <button
              key={tab.key}
              className={`${styles.tab} ${activeTab === tab.key ? styles.tabActive : ''}`}
              onClick={() => { setActiveTab(tab.key); setShowSearch(false); }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className={styles.contentArea}>
          {msg && (
            <div className={`${styles.msgBar} ${msg.includes('失败') || msg.startsWith('✗') ? styles.msgError : styles.msgSuccess}`} style={{ marginBottom: '1rem' }}>
              {msg}
            </div>
          )}

          {showSearch && (
            <div className={styles.searchResults}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span style={{ color: '#aaa', fontSize: '0.85rem' }}>搜索结果: {searchResults.length} 条</span>
                <button className={styles.actionBtn} onClick={() => { setShowSearch(false); setSearchResults([]); }}>关闭</button>
              </div>
              {searchResults.map(r => (
                <div key={r.id} className={styles.searchResultItem}>
                  <div className={styles.searchResultTitle}>
                    <span className={styles.searchResultName}>{r.title}</span>
                    <span className={styles.searchResultScore}>{(r.score * 100).toFixed(1)}%</span>
                  </div>
                  <div className={styles.searchResultText}>{r.content.slice(0, 300)}{r.content.length > 300 ? '...' : ''}</div>
                  {r.source && <div style={{ color: '#666', fontSize: '0.75rem', marginTop: '0.2rem' }}>来源: {r.source}</div>}
                </div>
              ))}
              {searchResults.length === 0 && <div className={styles.emptyState}>无匹配结果</div>}
            </div>
          )}

          {!showSearch && (
            <>
              {filteredItems.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.8rem' }}>
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
                        className={`${styles.actionBtn} ${styles.actionBtnPrimary}`}
                        onClick={handleDownloadSelectedItems}
                        style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem' }}
                      >
                        📥 批量下载 ({selectedItemIds.size})
                      </button>
                      <button
                        className={`${styles.actionBtn} ${styles.actionBtnPrimary}`}
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
                <div className={styles.emptyState}>
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
                  <div key={item.id} className={styles.itemRow} style={{ background: isSelected ? 'rgba(52,152,219,0.08)' : undefined }}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelectItem(item.id)}
                      style={{ cursor: 'pointer', marginRight: '0.4rem' }}
                    />
                    <span className={styles.itemIcon}>{typeIcon(item.type)}</span>
                    <div className={styles.itemInfo}>
                      <div className={styles.itemName}>{name}</div>
                      {item.source && <div className={styles.itemSource}>{item.source}</div>}
                    </div>
                    <div className={styles.itemMeta}>
                      {size !== undefined && <span className={styles.itemSize}>{formatBytes(size)}</span>}
                      {item.type === 'file' && <span className={styles.statusIcon} title={item.processingStatus}>{statusIcon(item.processingStatus)}</span>}
                      {item.type === 'file' && isFileMeta(item.content) && (
                        <button className={styles.downloadBtn} onClick={() => handleDownloadItem(item)} title="下载">📥</button>
                      )}
                      <button className={styles.deleteBtn} onClick={() => handleDeleteItem(item.id)}>删除</button>
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
        <div className={styles.overlay} onClick={() => setShowCreateBase(false)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalTitle}>新建知识库</div>
            <input
              className={styles.modalInput}
              placeholder="知识库名称"
              value={newBaseName}
              onChange={e => setNewBaseName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreateBase()}
              autoFocus
            />
            <div className={styles.modalActions}>
              <button className={styles.actionBtn} onClick={() => setShowCreateBase(false)}>取消</button>
              <button className={`${styles.actionBtn} ${styles.actionBtnPrimary}`} onClick={handleCreateBase}>创建</button>
            </div>
          </div>
        </div>
      )}

      {/* Rename Base Modal */}
      {showRenameBase && (
        <div className={styles.overlay} onClick={() => setShowRenameBase(false)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalTitle}>重命名知识库</div>
            <input
              className={styles.modalInput}
              placeholder="新名称"
              value={renameBaseName}
              onChange={e => setRenameBaseName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleRenameBase()}
              autoFocus
            />
            <div className={styles.modalActions}>
              <button className={styles.actionBtn} onClick={() => setShowRenameBase(false)}>取消</button>
              <button className={`${styles.actionBtn} ${styles.actionBtnPrimary}`} onClick={handleRenameBase}>确认</button>
            </div>
          </div>
        </div>
      )}

      {/* Add Note Modal */}
      {showAddNote && (
        <div className={styles.overlay} onClick={() => setShowAddNote(false)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalTitle}>添加笔记</div>
            <textarea
              className={styles.modalTextarea}
              placeholder="输入笔记内容..."
              value={noteContent}
              onChange={e => setNoteContent(e.target.value)}
              autoFocus
            />
            <div className={styles.modalActions}>
              <button className={styles.actionBtn} onClick={() => setShowAddNote(false)}>取消</button>
              <button className={`${styles.actionBtn} ${styles.actionBtnPrimary}`} onClick={handleAddNote}>添加</button>
            </div>
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {showSettings && (
        <div className={styles.overlay} onClick={() => setShowSettings(false)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()} style={{ maxHeight: '80vh', overflow: 'auto' }}>
            <div className={styles.modalTitle}>模型配置</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
              <div>
                <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '0.3rem' }}>嵌入模型</div>
                <select
                  className={styles.modalInput}
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
                    className={styles.modalInput}
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
                    className={styles.modalInput}
                    style={{ marginTop: '0.4rem' }}
                    type="password"
                    placeholder="API Key"
                    value={settingsEmbeddingApiKey}
                    onChange={e => setSettingsEmbeddingApiKey(e.target.value)}
                  />
                )}
                {(settingsEmbedding === 'openai' || settingsEmbedding === 'ollama') && (
                  <input
                    className={styles.modalInput}
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
                  className={styles.modalInput}
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
                    className={styles.modalInput}
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
                    className={styles.modalInput}
                    style={{ marginTop: '0.4rem' }}
                    type="password"
                    placeholder="API Key"
                    value={settingsRerankerApiKey}
                    onChange={e => setSettingsRerankerApiKey(e.target.value)}
                  />
                )}
                {settingsReranker === 'tei' && (
                  <input
                    className={styles.modalInput}
                    style={{ marginTop: '0.4rem' }}
                    placeholder="Base URL (可选，默认: http://localhost:8080)"
                    value={settingsRerankerBaseUrl}
                    onChange={e => setSettingsRerankerBaseUrl(e.target.value)}
                  />
                )}
              </div>
            </div>
            <div className={styles.modalActions}>
              <button className={styles.actionBtn} onClick={() => setShowSettings(false)}>取消</button>
              <button className={`${styles.actionBtn} ${styles.actionBtnPrimary}`} onClick={saveSettings}>保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
