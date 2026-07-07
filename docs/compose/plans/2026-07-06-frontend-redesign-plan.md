# 前端重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将单页 SPA 重构为三栏布局 + 纯路由架构，保留所有现有功能

**Architecture:** 渐进式迁移 — 先抽取共享模块，再建立布局骨架，最后逐页迁移。每个 Phase 完成后系统可正常运行。

**Tech Stack:** Next.js 14 App Router, React 18, Tailwind CSS v4, shadcn/ui, Framer Motion, Zustand, Lucide React

## Global Constraints

- 不改动任何后端 API
- 不改动现有组件内部逻辑（只改导入路径）
- 不删除任何现有功能
- CSS Modules 暂不迁移
- 保持现有 SSE + 轮询机制不变
- 所有页面组件使用 `'use client'` 指令

---

## Phase 1: 基础设施（Tasks 1-4）

### Task 1: 抽取共享模块

**Covers:** [S4]

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/constants.ts`
- Create: `frontend/src/lib/types.ts`

**Interfaces:**
- Produces: `apiBase()`, `fetchApi()`, `TEAM_COLORS`, `TEAM_LABELS`, `TEAM_ICONS`, `Message`, `TabType`

- [ ] **Step 1: 创建 api.ts**

```typescript
// frontend/src/lib/api.ts
declare global {
  interface Window {
    __API_BASE__?: string;
  }
}

export const apiBase = (): string =>
  window.__API_BASE__ || 'http://localhost:8000/api/v1';

export async function fetchApi<T = any>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(apiBase() + path, options);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail?.message || `请求失败: ${res.status}`);
  }
  return res.json();
}
```

- [ ] **Step 2: 创建 constants.ts**

```typescript
// frontend/src/lib/constants.ts

export const TEAM_COLORS: Record<string, string> = {
  coordinator: '#3B82F6',
  research_agent: '#6366F1',
  data_agent: '#10B981',
  analyzer_agent: '#F59E0B',
  modeler_agent: '#EC4899',
  algorithm_engineer_agent: '#8B5CF6',
  financial_analyst_agent: '#14B8A6',
  solver_agent: '#EF4444',
  writer_agent: '#06B6D4',
  peer_review_agent: '#F97316',
  experimentation_agent: '#A855F7',
  figure_agent: '#22D3EE',
  requirement_decomposer: '#84CC16',
  innovation_agent: '#E879F9',
  summary_agent: '#FB923C',
};

export const TEAM_LABELS: Record<string, string> = {
  coordinator: '协调者',
  research_agent: '研究员',
  data_agent: '数据分析师',
  analyzer_agent: '分析师',
  modeler_agent: '建模师',
  algorithm_engineer_agent: '算法工程师',
  financial_analyst_agent: '金融分析师',
  solver_agent: '求解器',
  writer_agent: '写作专家',
  peer_review_agent: '审稿人',
  experimentation_agent: '实验设计专家',
  figure_agent: '科研绘图师',
  requirement_decomposer: '需求分解器',
  innovation_agent: '创新发现专家',
  summary_agent: '总结专家',
  system: '系统',
  user: '你',
};

export const TEAM_ICONS: Record<string, string> = {
  coordinator: 'Users',
  research_agent: 'Search',
  data_agent: 'Database',
  analyzer_agent: 'BarChart3',
  modeler_agent: 'Box',
  algorithm_engineer_agent: 'Code2',
  financial_analyst_agent: 'TrendingUp',
  solver_agent: 'Cpu',
  writer_agent: 'PenTool',
  peer_review_agent: 'CheckCircle2',
  experimentation_agent: 'FlaskConical',
  figure_agent: 'Palette',
  requirement_decomposer: 'ListTodo',
  innovation_agent: 'Lightbulb',
  summary_agent: 'FileText',
};

export const TAB_META: Record<string, { title: string; subtitle: string }> = {
  dashboard: { title: '仪表盘', subtitle: '系统状态与快速开始' },
  generate: { title: '任务执行', subtitle: '实时监控 Agent 协作' },
  files: { title: '文件管理', subtitle: '数据文件与知识库' },
  pdf: { title: 'PDF 管理', subtitle: '论文解析与下载' },
  history: { title: '历史任务', subtitle: '任务记录与回溯' },
  agents: { title: 'Agent 管理', subtitle: '团队配置与模型路由' },
  workflows: { title: '工作流', subtitle: 'LangGraph 编排配置' },
  memory: { title: '记忆系统', subtitle: '经验教训与任务记忆' },
  environment: { title: '环境管理', subtitle: 'Conda / Venv 管理' },
  settings: { title: '系统设置', subtitle: 'Provider / MCP / 知识库' },
};
```

- [ ] **Step 3: 创建 types.ts**

```typescript
// frontend/src/lib/types.ts

export interface Message {
  id: string;
  sender: string;
  sender_label: string;
  content: string;
  type: string;
  timestamp: string;
}

export type TabType =
  | 'dashboard'
  | 'generate'
  | 'files'
  | 'pdf'
  | 'history'
  | 'agents'
  | 'workflows'
  | 'memory'
  | 'environment'
  | 'settings';

export type TaskStatus =
  | 'idle'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'paused'
  | 'phase1'
  | 'phase2'
  | 'retrying';
```

- [ ] **Step 4: 验证构建**

Run: `cd frontend && npx next build --no-lint 2>&1 | tail -20`
Expected: 构建成功，无 TypeScript 错误

- [ ] **Step 5: 提交**

```bash
cd frontend && git add src/lib/api.ts src/lib/constants.ts src/lib/types.ts && git commit -m "feat: extract shared api, constants, and types modules"
```

---

### Task 2: 创建 useLayoutStore

**Covers:** [S6]

**Files:**
- Create: `frontend/src/app/store/useLayoutStore.ts`

**Interfaces:**
- Produces: `useLayoutStore` with `sidebarCollapsed`, `detailPanelOpen`, `detailPanelContent`, `toggleSidebar`, `openDetailPanel`, `closeDetailPanel`

- [ ] **Step 1: 创建 store**

```typescript
// frontend/src/app/store/useLayoutStore.ts
import { create } from 'zustand';

interface LayoutState {
  sidebarCollapsed: boolean;
  detailPanelOpen: boolean;
  detailPanelContent: {
    type: 'task' | 'agent' | null;
    taskId?: string;
    agentName?: string;
  } | null;
  toggleSidebar: () => void;
  openDetailPanel: (content: LayoutState['detailPanelContent']) => void;
  closeDetailPanel: () => void;
}

export const useLayoutStore = create<LayoutState>((set) => ({
  sidebarCollapsed: false,
  detailPanelOpen: false,
  detailPanelContent: null,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  openDetailPanel: (content) => set({ detailPanelOpen: true, detailPanelContent: content }),
  closeDetailPanel: () => set({ detailPanelOpen: false, detailPanelContent: null }),
}));
```

- [ ] **Step 2: 验证构建**

Run: `cd frontend && npx next build --no-lint 2>&1 | tail -20`
Expected: 构建成功

- [ ] **Step 3: 提交**

```bash
cd frontend && git add src/app/store/useLayoutStore.ts && git commit -m "feat: add useLayoutStore for sidebar and detail panel state"
```

---

### Task 3: 更新 Sidebar 使用 Next.js Link

**Covers:** [S3]

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: `useLayoutStore` (from Task 2)
- Produces: Sidebar 使用 `next/link` 进行导航，不再接受 `onTabChange` 回调

- [ ] **Step 1: 重写 Sidebar**

将 `onTabChange` 回调替换为 `next/link` 的 `href` 导航。保留所有现有视觉效果。

关键改动：
1. `navItems` 每项增加 `href` 字段
2. `<button onClick={() => onTabChange(item.id)}` 改为 `<Link href={item.href}`
3. 使用 `usePathname()` 判断当前激活项
4. 移除 `activeTab` prop，改用路由自动判断
5. 新建任务按钮改为 `<Link href="/generate">`

完整代码：

```typescript
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
  Database,
  Workflow,
  Brain,
  Server,
  Layers,
} from 'lucide-react'
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
  { href: '/settings', label: '系统设置', icon: Settings },
]

export function Sidebar({ tasks = [] }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false)
  const pathname = usePathname()

  return (
    <motion.aside
      animate={{ width: collapsed ? 64 : 260 }}
      transition={{ duration: 0.2, ease: 'easeInOut' }}
      className="h-screen flex flex-col border-r border-border bg-slate-900/50 backdrop-blur-xl"
    >
      {/* Logo */}
      <div className="h-14 flex items-center gap-3 px-4 border-b border-border">
        <Link href="/" className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-secondary flex items-center justify-center">
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
              <span className="text-sm font-semibold text-foreground">SciAgent</span>
              <span className="text-xs text-muted-foreground ml-1">v7.3</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* New Task Button */}
      <div className="px-3 py-3">
        <Link
          href="/generate"
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
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <StatusDot status={task.status as any} size="sm" />
              <span className="truncate">{task.name}</span>
            </Link>
          ))}
        </div>
      )}

      {/* Collapse Toggle */}
      <div className="px-2 py-2 border-t border-border">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center gap-2 py-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors text-xs"
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          {!collapsed && <span>收起侧栏</span>}
        </button>
      </div>
    </motion.aside>
  )
}
```

- [ ] **Step 2: 验证构建**

Run: `cd frontend && npx next build --no-lint 2>&1 | tail -20`
Expected: 构建成功

- [ ] **Step 3: 提交**

```bash
cd frontend && git add src/components/layout/Sidebar.tsx && git commit -m "feat: refactor Sidebar to use Next.js Link routing"
```

---

### Task 4: 重写根布局为三栏结构

**Covers:** [S3]

**Files:**
- Modify: `frontend/src/app/layout.tsx`

**Interfaces:**
- Consumes: `Sidebar` (from Task 3), `TopBar`

- [ ] **Step 1: 重写 layout.tsx**

当前 layout.tsx 是 server component，需要改为 client component 以支持 Sidebar 的状态。

```typescript
// frontend/src/app/layout.tsx
'use client'

import './globals.css'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'
import { useLayoutStore } from './store/useLayoutStore'

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { sidebarCollapsed } = useLayoutStore()

  return (
    <html lang="zh-CN" className="dark">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Noto+Sans+SC:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-background text-foreground antialiased">
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <div className="flex-1 flex flex-col overflow-hidden">
            <TopBar title="SciAgent" subtitle="全自动科研助手" />
            <main className="flex-1 overflow-y-auto">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  )
}
```

- [ ] **Step 2: 验证构建**

Run: `cd frontend && npx next build --no-lint 2>&1 | tail -20`
Expected: 构建成功

- [ ] **Step 3: 提交**

```bash
cd frontend && git add src/app/layout.tsx && git commit -m "feat: rewrite root layout with three-column structure"
```

---

## Phase 2: 核心页面迁移（Tasks 5-9）

### Task 5: 迁移仪表盘页面

**Covers:** [S5]

**Files:**
- Modify: `frontend/src/app/page.tsx` (重写为仪表盘)

**Interfaces:**
- Consumes: `SystemStatusClient`, `ProblemInput`, `useAppStore`, `apiBase`

- [ ] **Step 1: 重写 page.tsx 为仪表盘**

将现有 page.tsx 中 `tab === 'dashboard'` 的内容提取为独立页面。移除所有 tab 切换逻辑、SSE 管理、任务提交逻辑（这些将迁移到各自的路由页面）。

```typescript
// frontend/src/app/page.tsx
'use client'

import SystemStatus from './components/SystemStatusClient'
import ProblemInput from './components/ProblemInput'
import { useAppStore } from './store/useAppStore'
import { apiBase } from '@/lib/api'
import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function DashboardPage() {
  const [submitting, setSubmitting] = useState(false)
  const [taskStatus, setTaskStatus] = useState('idle')
  const [progress, setProgress] = useState(0)
  const router = useRouter()
  const activeProjectId = useAppStore((s) => s.activeProjectId)
  const addTaskToProject = useAppStore((s) => s.addTaskToProject)

  const handleSubmit = async (params: {
    problemText: string
    projectName: string
    workflow: string
    template: string
    mode: string
    useCritique: boolean
    knowledgeBaseId: string | null
    knowledgeBaseIds: string[]
    dataSource: 'upload' | 'self_collect' | 'upload_and_collect'
    problemType: string
    dataFiles: string[]
  }) => {
    setSubmitting(true)
    try {
      const body: Record<string, any> = {
        problem_text: params.problemText,
        project_name: params.projectName,
        mode: params.mode,
        options: { workflow: params.workflow, template: params.template, use_critique: params.useCritique },
        data_files: params.dataFiles,
        data_source: params.dataSource,
        problem_type: params.problemType,
      }
      if (params.knowledgeBaseIds && params.knowledgeBaseIds.length > 0) {
        body.knowledge_base_ids = params.knowledgeBaseIds
      } else if (params.knowledgeBaseId) {
        body.knowledge_base_id = params.knowledgeBaseId
      }
      const res = await fetch(apiBase() + '/tasks/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok) {
        alert(data.detail?.message || `提交失败: ${res.status}`)
        return
      }
      const newTaskId = data.task_id
      if (activeProjectId && newTaskId) addTaskToProject(activeProjectId, newTaskId)
      router.push(`/task/${newTaskId}`)
    } catch (err) {
      console.error(err)
      alert('提交失败，请确认后端已启动')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="p-6 space-y-6">
      <SystemStatus />
      <ProblemInput
        onSubmit={handleSubmit}
        submitting={submitting}
        taskStatus={taskStatus}
        progress={progress}
      />
    </div>
  )
}
```

- [ ] **Step 2: 验证构建**

Run: `cd frontend && npx next build --no-lint 2>&1 | tail -20`
Expected: 构建成功

- [ ] **Step 3: 验证仪表盘页面**

Run: `cd frontend && npx next dev` (手动访问 http://localhost:3000)
Expected: 仪表盘正常显示，SystemStatus 和 ProblemInput 渲染正常

- [ ] **Step 4: 提交**

```bash
cd frontend && git add src/app/page.tsx && git commit -m "feat: migrate dashboard to standalone page"
```

---

### Task 6: 迁移任务执行页面

**Covers:** [S5, S6]

**Files:**
- Create: `frontend/src/app/task/[id]/page.tsx`

**Interfaces:**
- Consumes: `useTaskState`, `useAppStore`, `apiBase`, `Message` type, `PreFlightPanel`, `CameraReadyPanel`, `DiscussionPanel`, `StageProgress`

- [ ] **Step 1: 创建 task/[id] 页面**

将现有 page.tsx 中 `tab === 'generate'` 的全部逻辑迁移到这里。这是最复杂的页面，包含 SSE、阶段管理、暂停/恢复/取消等。

```typescript
// frontend/src/app/task/[id]/page.tsx
'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTaskState } from '@/app/hooks/useTaskState'
import { useAppStore } from '@/app/store/useAppStore'
import { apiBase } from '@/lib/api'
import { Message } from '@/lib/types'
import { PreFlightPanel, PreflightReport } from '@/app/components/PreFlightPanel'
import { CameraReadyPanel } from '@/app/components/CameraReadyPanel'
import DiscussionPanel from '@/app/components/DiscussionPanel'
import StageProgress from '@/app/components/StageProgress'

export default function TaskDetailPage() {
  const params = useParams()
  const taskId = params.id as string
  const router = useRouter()

  const [taskStatus, setTaskStatus] = useState<string>('idle')
  const [progress, setProgress] = useState(0)
  const [currentStep, setCurrentStep] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [eventSource, setEventSource] = useState<EventSource | null>(null)
  const taskState = useTaskState({ taskId })
  const [paused, setPaused] = useState(false)
  const [resuming, setResuming] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [phase, setPhase] = useState<'idle' | 'phase1' | 'phase2_confirm' | 'phase2'>('idle')
  const [subProblems, setSubProblems] = useState<string[]>([])
  const [solveMode, setSolveMode] = useState<'batch' | 'sequential'>('batch')
  const [submitting, setSubmitting] = useState(false)
  const [preflightReport, setPreflightReport] = useState<PreflightReport | null>(null)
  const [showDiscussion, setShowDiscussion] = useState(false)
  const [pauseData, setPauseData] = useState<any>(null)

  const activeProjectId = useAppStore((s) => s.activeProjectId)

  // Sync task state
  useEffect(() => {
    if (taskState.state) {
      setTaskStatus(taskState.state.name)
      setProgress(taskState.state.progressPercentage)
      setCurrentStep(taskState.state.currentStep)
    }
  }, [taskState.state])

  // Load pause data
  useEffect(() => {
    if (paused && taskId) loadPauseData()
  }, [paused])

  // SSE streaming
  const startSSE = useCallback((id: string) => {
    if (eventSource) eventSource.close()
    const es = new EventSource(apiBase() + '/tasks/' + id + '/stream')
    setEventSource(es)
    const msgPoll = setInterval(async () => {
      try {
        const res = await fetch(apiBase() + '/tasks/' + id + '/messages')
        if (res.ok) {
          const msgs = await res.json()
          const newMsgs = msgs.map((m: any) => ({
            id: m.id, sender: m.sender,
            sender_label: m.sender_label || m.sender,
            content: m.content, type: m.type || 'text', timestamp: m.timestamp,
          }))
          setMessages(prev => {
            if (prev.length !== newMsgs.length) return newMsgs
            if (prev.length > 0 && newMsgs.length > 0 && prev[prev.length - 1].id !== newMsgs[newMsgs.length - 1].id) return newMsgs
            return prev
          })
        }
      } catch {}
    }, 1000)
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data)
        setTaskStatus(d.status)
        setProgress(d.progress || 0)
        setCurrentStep(d.current_step || '')
        if (d.status === 'paused') { setPaused(true); es.close(); clearInterval(msgPoll) }
        if (d.status === 'phase1_completed') {
          const wf = d.workflow_type || ''
          if (wf === 'deep_research' || wf === 'research_survey') { autoConfirmSubProblems(id) }
          else { setPhase('phase2_confirm'); loadSubProblems(id) }
          es.close(); clearInterval(msgPoll)
        }
        if (['completed', 'failed', 'cancelled'].includes(d.status)) { es.close(); clearInterval(msgPoll) }
      } catch {}
    }
    es.onerror = () => { es.close(); clearInterval(msgPoll) }
  }, [eventSource])

  // Auto-start SSE on mount
  useEffect(() => {
    if (taskId) startSSE(taskId)
    return () => { if (eventSource) eventSource.close() }
  }, [taskId])

  // ... (loadSubProblems, handlePhase1, handlePhase2, autoConfirmSubProblems,
  //      handleConfirmSubproblems, handlePause, handleResume, handleCancel,
  //      handleEditAndContinue, loadPauseData — 同原 page.tsx 中对应函数)

  return (
    <div className="p-6 space-y-4">
      {/* Phase Controls */}
      {(phase === 'idle' && taskId && taskStatus !== 'running' && taskStatus !== 'completed') && (
        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-primary font-semibold">分阶段工作流</span>
            <button onClick={handlePhase1} className="px-3 py-1.5 rounded-lg bg-primary/10 border border-primary/20 text-primary text-sm hover:bg-primary/20 transition-colors">
              启动阶段1（分析+数据）
            </button>
          </div>
          <p className="text-sm text-muted-foreground">阶段1完成后可确认子问题列表，再启动阶段2建模求解</p>
        </div>
      )}

      {/* Phase 2 Confirm */}
      {phase === 'phase2_confirm' && (
        <div className="rounded-xl border border-success/20 bg-success/5 p-4">
          <span className="text-success font-semibold block mb-3">阶段1已完成 — 确认子问题后启动阶段2</span>
          <div className="space-y-2 mb-4">
            {subProblems.map((sp, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <span className="text-warning text-sm w-5">{idx + 1}.</span>
                <input value={sp} onChange={e => { const next = [...subProblems]; next[idx] = e.target.value; setSubProblems(next) }}
                  className="flex-1 px-3 py-2 rounded-lg bg-muted border border-border text-foreground text-sm" />
                <button onClick={() => setSubProblems(subProblems.filter((_, i) => i !== idx))} className="px-2 py-1 rounded text-error text-xs hover:bg-error/10">✕</button>
              </div>
            ))}
            <button onClick={() => setSubProblems([...subProblems, ''])} className="px-3 py-1 rounded-lg bg-primary/10 text-primary text-xs hover:bg-primary/20">+ 添加子问题</button>
          </div>
          <div className="flex items-center gap-4 mb-4">
            <span className="text-sm text-muted-foreground">求解策略：</span>
            <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
              <input type="radio" checked={solveMode === 'sequential'} onChange={() => setSolveMode('sequential')} /> 逐个递进
            </label>
            <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
              <input type="radio" checked={solveMode === 'batch'} onChange={() => setSolveMode('batch')} /> 批量并行
            </label>
          </div>
          <div className="flex gap-2">
            <button onClick={handleConfirmSubproblems} disabled={submitting} className="btn-gradient">启动阶段2</button>
            <button onClick={() => { setPhase('idle'); setSubProblems([]) }} className="px-4 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">取消</button>
          </div>
        </div>
      )}

      {/* Progress Bar */}
      {(taskStatus === 'running' || taskStatus === 'phase1' || taskStatus === 'phase2') && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{currentStep || '准备中...'}</span>
            <span className="text-primary font-medium">{Math.round(progress)}%</span>
          </div>
          <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
            <div className="h-full rounded-full bg-gradient-to-r from-primary to-secondary transition-all duration-500" style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}

      {/* Control Buttons */}
      {taskId && taskStatus !== 'completed' && taskStatus !== 'cancelled' && (
        <div className="flex gap-2">
          {paused ? (
            <button onClick={handleResume} disabled={resuming} className="btn-gradient">{resuming ? '恢复中...' : '恢复'}</button>
          ) : (
            <button onClick={handlePause} className="px-4 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">暂停</button>
          )}
          <button onClick={handleCancel} disabled={cancelling} className="px-4 py-2 rounded-lg border border-error/30 text-error text-sm hover:bg-error/10 transition-colors">
            {cancelling ? '取消中...' : '终止'}
          </button>
        </div>
      )}

      {/* Preflight Report */}
      {preflightReport && <PreFlightPanel report={preflightReport} />}

      {/* Discussion Panel Toggle */}
      {taskId && (taskStatus === 'running' || taskStatus === 'paused') && (
        <button onClick={() => setShowDiscussion(!showDiscussion)} className="px-4 py-2 rounded-lg bg-primary/10 border border-primary/20 text-primary text-sm hover:bg-primary/20 transition-colors">
          {showDiscussion ? '关闭讨论面板' : 'Agent 讨论面板'}
        </button>
      )}

      {showDiscussion && taskId && <DiscussionPanel taskId={taskId} onClose={() => setShowDiscussion(false)} />}

      {/* Camera Ready */}
      {taskState.state?.name === 'completed' && taskId && (
        <CameraReadyPanel taskId={taskId} templateId={taskState.state?.templateId || 'math_modeling'} />
      )}
    </div>
  )
}
```

注意：完整实现需要包含所有 handler 函数（handlePhase1, handlePhase2 等），代码量约 250 行。以上为骨架，实施时需从原 page.tsx 复制完整逻辑。

- [ ] **Step 2: 验证构建**

Run: `cd frontend && npx next build --no-lint 2>&1 | tail -20`

- [ ] **Step 3: 提交**

```bash
cd frontend && mkdir -p src/app/task/\[id\] && git add src/app/task/ && git commit -m "feat: create task execution monitoring page"
```

---

### Task 7: 迁移报告查看页面

**Covers:** [S5]

**Files:**
- Create: `frontend/src/app/task/[id]/report/page.tsx`

**Interfaces:**
- Consumes: `PaperPreview`, `PaperList`, `apiBase`

- [ ] **Step 1: 创建报告页面**

```typescript
// frontend/src/app/task/[id]/report/page.tsx
'use client'

import { useParams } from 'next/navigation'
import { useState, useEffect } from 'react'
import { apiBase } from '@/lib/api'
import PaperPreview from '@/app/components/PaperPreview'
import PaperList from '@/app/components/PaperList'

export default function ReportPage() {
  const params = useParams()
  const taskId = params.id as string
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(apiBase() + '/tasks/' + taskId + '/result')
        if (res.ok) setResult(await res.json())
      } catch {}
      setLoading(false)
    }
    load()
  }, [taskId])

  if (loading) return <div className="p-6 text-muted-foreground">加载中...</div>
  if (!result) return <div className="p-6 text-muted-foreground">暂无报告</div>

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-xl font-semibold">研究报告</h2>
      <PaperList result={result} />
      <PaperPreview result={result} />
    </div>
  )
}
```

- [ ] **Step 2: 验证构建 + 提交**

```bash
cd frontend && npx next build --no-lint 2>&1 | tail -20
git add src/app/task/\[id\]/report/ && git commit -m "feat: create report viewer page"
```

---

### Task 8: 迁移历史任务页面

**Covers:** [S5]

**Files:**
- Create: `frontend/src/app/history/page.tsx`

**Interfaces:**
- Consumes: `TaskHistory`

- [ ] **Step 1: 创建历史页面**

```typescript
// frontend/src/app/history/page.tsx
'use client'

import TaskHistory from '@/app/components/TaskHistory'

export default function HistoryPage() {
  return (
    <div className="p-6">
      <TaskHistory />
    </div>
  )
}
```

- [ ] **Step 2: 验证构建 + 提交**

```bash
cd frontend && npx next build --no-lint 2>&1 | tail -20
git add src/app/history/ && git commit -m "feat: create history page"
```

---

### Task 9: 迁移 Agent 管理页面

**Covers:** [S5]

**Files:**
- Create: `frontend/src/app/agents/page.tsx`

**Interfaces:**
- Consumes: `AgentManager`

- [ ] **Step 1: 创建 Agent 页面**

```typescript
// frontend/src/app/agents/page.tsx
'use client'

import AgentManager from '@/app/components/AgentManager'

export default function AgentsPage() {
  return (
    <div className="p-6">
      <AgentManager />
    </div>
  )
}
```

- [ ] **Step 2: 验证构建 + 提交**

```bash
cd frontend && npx next build --no-lint 2>&1 | tail -20
git add src/app/agents/ && git commit -m "feat: create agents management page"
```

---

## Phase 3: 管理页面迁移（Tasks 10-14）

### Task 10: 迁移文件管理页面

**Covers:** [S5]

**Files:**
- Create: `frontend/src/app/files/page.tsx`

- [ ] **Step 1: 创建文件管理页面**

```typescript
// frontend/src/app/files/page.tsx
'use client'

import FileManager from '@/app/components/FileManager'

export default function FilesPage() {
  return (
    <div className="p-6">
      <FileManager />
    </div>
  )
}
```

注意：`FileManager` 原本接受 `taskId` prop，需要检查是否必须。如果不是必须，可以不传。

- [ ] **Step 2: 验证构建 + 提交**

```bash
cd frontend && npx next build --no-lint 2>&1 | tail -20
git add src/app/files/ && git commit -m "feat: create files management page"
```

---

### Task 11: 迁移 PDF 管理页面

**Covers:** [S5]

**Files:**
- Create: `frontend/src/app/pdf/page.tsx`

- [ ] **Step 1: 创建 PDF 页面**

```typescript
// frontend/src/app/pdf/page.tsx
'use client'

import PdfManager from '@/app/components/PdfManager'

export default function PdfPage() {
  return (
    <div className="p-6">
      <PdfManager />
    </div>
  )
}
```

- [ ] **Step 2: 验证构建 + 提交**

```bash
cd frontend && npx next build --no-lint 2>&1 | tail -20
git add src/app/pdf/ && git commit -m "feat: create PDF management page"
```

---

### Task 12: 迁移工作流页面

**Covers:** [S5]

**Files:**
- Create: `frontend/src/app/workflows/page.tsx`

- [ ] **Step 1: 创建工作流页面**

```typescript
// frontend/src/app/workflows/page.tsx
'use client'

import WorkflowManager from '@/app/components/WorkflowManager'

export default function WorkflowsPage() {
  return (
    <div className="p-6">
      <WorkflowManager />
    </div>
  )
}
```

- [ ] **Step 2: 验证构建 + 提交**

```bash
cd frontend && npx next build --no-lint 2>&1 | tail -20
git add src/app/workflows/ && git commit -m "feat: create workflows page"
```

---

### Task 13: 迁移记忆系统页面

**Covers:** [S5]

**Files:**
- Create: `frontend/src/app/memory/page.tsx`

- [ ] **Step 1: 创建记忆页面**

```typescript
// frontend/src/app/memory/page.tsx
'use client'

import MemoryManager from '@/app/components/MemoryManager'

export default function MemoryPage() {
  return (
    <div className="p-6">
      <MemoryManager />
    </div>
  )
}
```

- [ ] **Step 2: 验证构建 + 提交**

```bash
cd frontend && npx next build --no-lint 2>&1 | tail -20
git add src/app/memory/ && git commit -m "feat: create memory page"
```

---

### Task 14: 迁移环境管理页面

**Covers:** [S5]

**Files:**
- Create: `frontend/src/app/environment/page.tsx`

- [ ] **Step 1: 创建环境管理页面**

```typescript
// frontend/src/app/environment/page.tsx
'use client'

import EnvironmentManager from '@/app/components/EnvironmentManager'

export default function EnvironmentPage() {
  return (
    <div className="p-6">
      <EnvironmentManager />
    </div>
  )
}
```

- [ ] **Step 2: 验证构建 + 提交**

```bash
cd frontend && npx next build --no-lint 2>&1 | tail -20
git add src/app/environment/ && git commit -m "feat: create environment management page"
```

---

### Task 15: 迁移设置页面

**Covers:** [S5]

**Files:**
- Create: `frontend/src/app/settings/page.tsx`

**Interfaces:**
- Consumes: `SettingsPage` (existing component)

- [ ] **Step 1: 创建设置页面**

```typescript
// frontend/src/app/settings/page.tsx
'use client'

import SettingsPage from '@/app/components/SettingsPage'

export default function Settings() {
  return (
    <div className="p-6">
      <SettingsPage />
    </div>
  )
}
```

- [ ] **Step 2: 验证构建 + 提交**

```bash
cd frontend && npx next build --no-lint 2>&1 | tail -20
git add src/app/settings/ && git commit -m "feat: create settings page"
```

---

## Phase 4: 清理（Task 16）

### Task 16: 清理旧代码 + 最终验证

**Covers:** [S7, S8]

**Files:**
- Modify: 所有引用 `apiBase()` 的组件（改用 `@/lib/api`）
- Modify: 所有引用 `TEAM_COLORS`/`TEAM_LABELS` 的组件（改用 `@/lib/constants`）

**Interfaces:**
- Consumes: `apiBase` from `@/lib/api`, `TEAM_COLORS`/`TEAM_LABELS` from `@/lib/constants`

- [ ] **Step 1: 更新所有组件的导入**

搜索并替换所有文件中的：
- `const apiBase = () => window.__API_BASE__ || ...` → `import { apiBase } from '@/lib/api'`
- 内联的 `TEAM_COLORS` / `TEAM_LABELS` 定义 → `import { TEAM_COLORS, TEAM_LABELS } from '@/lib/constants'`

涉及的文件（需要逐个检查）：
- `src/app/components/AgentChat.tsx`
- `src/app/components/TaskDetail.tsx`
- `src/app/components/DiscussionPanel.tsx`
- `src/app/components/ProblemInput.tsx`
- `src/app/components/FileManager.tsx`
- `src/app/components/AgentManager.tsx`
- `src/app/components/SettingsPage.tsx`
- `src/app/components/McpManager.tsx`
- `src/app/components/KnowledgeBaseManager.tsx`
- `src/app/components/ProviderSettings.tsx`
- `src/app/components/SystemStatusClient.tsx`
- `src/app/components/MemoryManager.tsx`
- `src/app/components/EnvironmentManager.tsx`
- `src/app/components/PdfManager.tsx`
- `src/app/components/WorkflowManager.tsx`

- [ ] **Step 2: 验证构建**

Run: `cd frontend && npx next build --no-lint 2>&1 | tail -30`
Expected: 构建成功，无 TypeScript 错误

- [ ] **Step 3: 端到端验证**

手动测试以下流程：
1. 访问 `/` — 仪表盘正常显示
2. 点击侧边栏导航 — 各页面正常切换
3. 访问 `/generate` — 任务创建表单正常
4. 提交任务后跳转到 `/task/[id]` — 执行监控正常
5. 访问 `/history` — 历史任务列表正常
6. 访问 `/settings` — 设置页面正常
7. 浏览器前进后退 — 路由正确响应

- [ ] **Step 4: 最终提交**

```bash
cd frontend && git add -A && git commit -m "feat: complete frontend routing migration - replace SPA tabs with Next.js routes"
```

---

## Summary

| Phase | Tasks | 描述 |
|-------|-------|------|
| 1 | 1-4 | 基础设施：共享模块 + Layout Store + Sidebar 路由化 + 三栏布局 |
| 2 | 5-9 | 核心页面：Dashboard + Task + Report + History + Agents |
| 3 | 10-15 | 管理页面：Files + PDF + Workflows + Memory + Environment + Settings |
| 4 | 16 | 清理：统一导入 + 最终验证 |

总计 16 个 Task，每个 Task 独立可验证。
