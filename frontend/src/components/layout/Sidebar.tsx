'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  Plus,
  FileText,
  Settings,
  History,
  ChevronLeft,
  ChevronRight,
  Bot,
  Workflow,
  Brain,
  Server,
  Layers,
  Menu,
  X,
  Database,
  Sun,
  Moon,
} from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'
import { useLayoutStore } from '@/app/store/useLayoutStore'
import { cn } from '@/lib/utils'
import { StatusDot } from '@/components/ui/status-dot'

interface SidebarProps {
  tasks?: Array<{ id: string; name: string; status: string }>
}

const navItems = [
  { href: '/', label: '仪表盘', icon: Layers },
  { href: '/generate', label: '新建任务', icon: Plus },
  { href: '/history', label: '历史任务', icon: History },
  { href: '/agents', label: 'Agent 管理', icon: Bot },
  { href: '/workflows', label: '工作流', icon: Workflow },
  { href: '/files', label: '文件管理', icon: FileText },
  { href: '/pdf', label: 'PDF 管理', icon: FileText },
  { href: '/memory', label: '记忆系统', icon: Brain },
  { href: '/environment', label: '环境管理', icon: Server },
  { href: '/knowledge', label: '知识库', icon: Database },
  { href: '/settings', label: '系统设置', icon: Settings },
]

export function Sidebar({ tasks = [] }: SidebarProps) {
  const { sidebarCollapsed: collapsed, toggleSidebar } = useLayoutStore()
  const [mobileOpen, setMobileOpen] = useState(false)
  const pathname = usePathname()
  const { theme, toggleTheme } = useTheme()

  const sidebarContent = (
    <>
      {/* Logo */}
      <div className="h-14 flex items-center gap-3 px-4 border-b border-border">
        <Link href="/" className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-secondary flex items-center justify-center" onClick={() => setMobileOpen(false)}>
          <span className="text-white text-sm font-bold">M</span>
        </Link>
        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: 'auto' }}
              exit={{ opacity: 0, width: 0 }}
              className="overflow-hidden whitespace-nowrap"
            >
              <span className="text-sm font-semibold text-foreground">LabAgent</span>
              <span className="text-xs text-muted-foreground ml-1">v8.2</span>
            </motion.div>
          )}
        </AnimatePresence>
        {/* Mobile close button */}
        <button
          onClick={() => setMobileOpen(false)}
          className="md:hidden ml-auto p-1 rounded text-muted-foreground hover:text-foreground"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* New Task Button */}
      <div className="px-3 py-3">
        <Link
          href="/generate"
          onClick={() => setMobileOpen(false)}
          className={cn(
            'w-full flex items-center justify-center gap-2 rounded-lg font-medium',
            'bg-gradient-to-r from-primary to-secondary text-white',
            'hover:shadow-glow-lg transition-all duration-200',
            collapsed ? 'h-9 w-9 p-0' : 'h-9 px-4'
          )}
        >
          <Plus className="w-4 h-4" />
          {!collapsed && <span className="text-sm">新建任务</span>}
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-1">
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = pathname === item.href ||
            (item.href !== '/' && pathname.startsWith(item.href))
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setMobileOpen(false)}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium',
                'transition-colors duration-150 mb-0.5',
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted',
                collapsed && 'justify-center px-0'
              )}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          )
        })}
      </nav>

      {/* Recent Tasks */}
      {!collapsed && tasks.length > 0 && (
        <div className="px-3 py-3 border-t border-border">
          <div className="text-xs font-medium text-muted-foreground mb-2 px-1">最近任务</div>
          {tasks.slice(0, 3).map((task) => (
            <Link
              key={task.id}
              href={`/task/${task.id}`}
              onClick={() => setMobileOpen(false)}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <StatusDot status={task.status as any} size="sm" />
              <span className="truncate">{task.name}</span>
            </Link>
          ))}
        </div>
      )}

      {/* Theme Toggle (desktop only) */}
      <div className="px-2 py-1 hidden md:block">
        <button
          onClick={toggleTheme}
          className="w-full flex items-center justify-center gap-2 py-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors text-xs"
        >
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          <span>{theme === 'dark' ? '浅色模式' : '深色模式'}</span>
        </button>
      </div>

      {/* Collapse Toggle (desktop only) */}
      <div className="px-2 py-2 border-t border-border hidden md:block">
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center justify-center gap-2 py-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors text-xs"
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          {!collapsed && <span>收起侧栏</span>}
        </button>
      </div>
    </>
  )

  return (
    <>
      {/* Mobile hamburger */}
      <button
        onClick={() => setMobileOpen(true)}
        className="md:hidden fixed top-3 left-3 z-50 p-2 rounded-lg bg-card/80 backdrop-blur border border-border text-muted-foreground hover:text-foreground transition-colors"
      >
        <Menu className="w-5 h-5" />
      </button>

      {/* Mobile overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="md:hidden fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Desktop sidebar */}
      <motion.aside
        animate={{ width: collapsed ? 64 : 260 }}
        transition={{ duration: 0.2, ease: 'easeInOut' }}
        className="hidden md:flex h-screen flex-col border-r border-border bg-slate-900/50 backdrop-blur-xl"
      >
        {sidebarContent}
      </motion.aside>

      {/* Mobile sidebar */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.aside
            initial={{ x: -280 }}
            animate={{ x: 0 }}
            exit={{ x: -280 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className="md:hidden fixed inset-y-0 left-0 z-50 w-[260px] flex flex-col border-r border-border bg-slate-900/50 backdrop-blur-xl"
          >
            {sidebarContent}
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  )
}
