'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { Search, Sun, Moon, Bell, FileText, Loader2, CheckCircle2, XCircle, Clock, AlertTriangle, Pencil, Save } from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'
import { usePathname, useRouter } from 'next/navigation'
import { cn } from '@/lib/utils'
import { apiBase } from '@/lib/api'
import { useDesignStore } from '@/lib/design-mode/store'

interface TopBarProps {
  title: string
  subtitle?: string
  className?: string
}

interface TaskResult {
  task_id: string
  problem_text: string
  status: string
  project_name?: string
  created_at?: number
}

export function TopBar({ title, subtitle, className }: TopBarProps) {
  const { theme, toggleTheme } = useTheme()
  const designMode = useDesignStore((s) => s.mode)
  const toggleDesign = useDesignStore((s) => s.toggleMode)
  const exportJSON = useDesignStore((s) => s.exportJSON)
  const markSaved = useDesignStore((s) => s.markSaved)
  const [saving, setSaving] = useState(false)
  const handleSave = async () => {
    setSaving(true)
    try {
      await fetch('/api/design', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: exportJSON(),
      })
      markSaved()
    } catch (e) {
      console.error('保存设计失败', e)
    } finally {
      setSaving(false)
    }
  }
  const [showSearch, setShowSearch] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<TaskResult[]>([])
  const [searching, setSearching] = useState(false)
  const [showNotif, setShowNotif] = useState(false)
  const [notifTasks, setNotifTasks] = useState<TaskResult[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const notifRef = useRef<HTMLDivElement>(null)
  const router = useRouter()

  // Close notification on outside click
  useEffect(() => {
    if (!showNotif) return
    const handler = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotif(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showNotif])

  // Ctrl+K / Cmd+K to open search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setShowSearch(prev => !prev)
      }
      if (e.key === 'Escape') { setShowSearch(false); setShowNotif(false) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  useEffect(() => {
    if (showSearch) {
      setTimeout(() => inputRef.current?.focus(), 100)
      setQuery('')
      setResults([])
    }
  }, [showSearch])

  // Fetch notifications on mount and every 30s
  useEffect(() => {
    const fetchNotif = async () => {
      try {
        const res = await fetch(apiBase() + '/tasks')
        if (res.ok) {
          const tasks: TaskResult[] = await res.json()
          // Show recent completed/failed tasks as notifications
          setNotifTasks(tasks
            .filter(t => ['completed', 'failed', 'cancelled'].includes(t.status))
            .sort((a, b) => (b.created_at || 0) - (a.created_at || 0))
            .slice(0, 8))
        }
      } catch {}
    }
    fetchNotif()
    const interval = setInterval(fetchNotif, 30000)
    return () => clearInterval(interval)
  }, [])

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); return }
    setSearching(true)
    try {
      const res = await fetch(apiBase() + '/tasks')
      if (res.ok) {
        const tasks: TaskResult[] = await res.json()
        const lower = q.toLowerCase()
        setResults(tasks.filter(t =>
          (t.problem_text || '').toLowerCase().includes(lower) ||
          (t.task_id || '').toLowerCase().includes(lower) ||
          (t.project_name || '').toLowerCase().includes(lower)
        ).slice(0, 10))
      }
    } catch {} finally { setSearching(false) }
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => doSearch(query), 300)
    return () => clearTimeout(timer)
  }, [query, doSearch])

  const statusLabel = (s: string) => {
    const m: Record<string, string> = { completed: '已完成', running: '运行中', failed: '失败', cancelled: '已取消', idle: '空闲' }
    return m[s] || s
  }

  return (
    <>
      <header
        data-design-id="topbar:header"
        className={cn(
          'h-14 flex items-center justify-between px-6 border-b border-border',
          'bg-background/80 backdrop-blur-sm',
          className
        )}
      >
        <div data-design-id="topbar:title">
          <h1 className="text-base font-semibold text-foreground">{title}</h1>
          {subtitle && (
            <p className="text-xs text-muted-foreground">{subtitle}</p>
          )}
        </div>

        <div data-design-id="topbar:actions" className="flex items-center gap-3">
          {/* Search —— 拉长为标准按钮的 1.5 倍宽（设计模式定死） */}
          <button
            data-design-id="topbar:btn-search"
            onClick={() => setShowSearch(true)}
            className="inline-flex h-9 w-[54px] items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title="搜索 (Ctrl+K)"
          >
            <Search className="w-4 h-4" />
          </button>

          {/* Notifications */}
          <div className="relative inline-flex" ref={notifRef}>
            <button
              data-design-id="topbar:btn-notif"
              onClick={() => { setShowNotif(prev => !prev); setShowSearch(false) }}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors relative"
            >
              <Bell className="w-4 h-4" />
              {notifTasks.length > 0 && (
                <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-error" />
              )}
            </button>
            {showNotif && (
              <div data-design-exclude="topbar" className="absolute right-0 top-full mt-2 w-[360px] bg-card border border-border rounded-xl shadow-md z-50" onClick={e => e.stopPropagation()}>
                <div className="flex justify-between items-center px-4 py-3 border-b border-border">
                  <span className="text-foreground font-semibold text-sm">通知</span>
                  <button onClick={() => setShowNotif(false)} className="text-muted-foreground hover:text-foreground text-xs">关闭</button>
                </div>
                <div className="max-h-[320px] overflow-y-auto">
                  {notifTasks.length === 0 ? (
                    <div className="py-8 text-center text-muted-foreground text-sm">暂无通知</div>
                  ) : notifTasks.map(t => (
                    <button
                      key={t.task_id}
                      className="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/50 transition-colors text-left border-b border-border last:border-0"
                      onClick={() => { setShowNotif(false); router.push(`/task/${t.task_id}`) }}
                    >
                      {t.status === 'completed' && <CheckCircle2 className="w-4 h-4 text-success shrink-0" />}
                      {t.status === 'failed' && <XCircle className="w-4 h-4 text-error shrink-0" />}
                      {t.status === 'cancelled' && <AlertTriangle className="w-4 h-4 text-warning shrink-0" />}
                      <div className="flex-1 min-w-0">
                        <div className="text-foreground text-sm truncate">{t.problem_text || t.task_id}</div>
                        <div className="text-muted-foreground text-xs">{statusLabel(t.status)} · {t.task_id.slice(0, 8)}</div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Theme Toggle */}
          <button
            data-design-id="topbar:btn-theme"
            onClick={toggleTheme}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>

          {/* Design Mode Toggle（桌面端创作工具）—— exclude：必须保留功能（进/出设计模式入口） */}
          <button
            data-design-exclude="topbar"
            onClick={toggleDesign}
            className={cn(
              'hidden md:inline-flex h-9 w-9 items-center justify-center rounded-lg transition-colors',
              designMode === 'edit'
                ? 'text-warning bg-warning/10'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted',
            )}
            title="设计模式"
          >
            <Pencil className="w-4 h-4" />
          </button>

          {/* 设计模式：保存（落盘交接物，仅 edit 模式显示） */}
          {designMode === 'edit' && (
            <button
              data-design-exclude="topbar"
              onClick={handleSave}
              disabled={saving}
              className="hidden md:inline-flex items-center gap-1.5 h-9 px-4 rounded-lg text-sm bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
              title="保存设计（落盘交接给 Claude 写回源码）"
            >
              <Save className="w-3.5 h-3.5" />
              {saving ? '保存中…' : '保存'}
            </button>
          )}
        </div>
      </header>

      {/* 全局搜索弹窗 */}
      {showSearch && (
        <div data-design-exclude="topbar" className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/50" onClick={() => setShowSearch(false)}>
          <div className="bg-card border border-border rounded-xl w-[520px] shadow-md" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
              <Search className="w-4 h-4 text-muted-foreground shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="搜索任务... (Ctrl+K)"
                className="flex-1 bg-transparent text-foreground text-sm outline-none placeholder:text-muted-foreground"
              />
              {searching && <Loader2 className="w-4 h-4 text-muted-foreground animate-spin" />}
              <kbd className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded border border-border">ESC</kbd>
            </div>
            <div className="max-h-[300px] overflow-y-auto">
              {query && results.length === 0 && !searching && (
                <div className="py-8 text-center text-muted-foreground text-sm">无匹配结果</div>
              )}
              {!query && (
                <div className="py-8 text-center text-muted-foreground text-sm">输入关键词搜索任务</div>
              )}
              {results.map(t => (
                <button
                  key={t.task_id}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/50 transition-colors text-left"
                  onClick={() => { setShowSearch(false); router.push(`/task/${t.task_id}`) }}
                >
                  <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-foreground text-sm truncate">{t.problem_text || t.task_id}</div>
                    <div className="text-muted-foreground text-xs">{statusLabel(t.status)} · {t.task_id.slice(0, 8)}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
