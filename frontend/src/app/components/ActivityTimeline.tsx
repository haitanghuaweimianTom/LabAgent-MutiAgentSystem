'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { StatusDot } from '@/components/ui/status-dot'
import { apiBase } from '@/lib/api'
import { Activity } from 'lucide-react'

interface TaskInfo {
  task_id: string
  problem_text: string
  status: string
  created_at: string
  completed_at?: string
}

const STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  running: '进行中',
  phase1: '阶段1',
  phase2: '阶段2',
  failed: '失败',
  cancelled: '已取消',
  paused: '已暂停',
  pending: '等待中',
}

const STATUS_DOT_MAP: Record<string, 'completed' | 'running' | 'failed' | 'pending' | 'idle'> = {
  completed: 'completed',
  running: 'running',
  phase1: 'running',
  phase2: 'running',
  failed: 'failed',
  cancelled: 'failed',
  paused: 'pending',
  pending: 'pending',
}

function formatTime(iso: string) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06 },
  },
}

const itemVariants = {
  hidden: { opacity: 0, x: -12 },
  show: { opacity: 1, x: 0 },
}

export function ActivityTimeline() {
  const [tasks, setTasks] = useState<TaskInfo[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function fetchTasks() {
      try {
        const res = await fetch(apiBase() + '/tasks')
        const data = await res.json()
        if (!cancelled) {
          setTasks(data.slice(0, 8))
        }
      } catch {
        // ignore — show empty state
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchTasks()
    const interval = setInterval(fetchTasks, 10000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  return (
    <div className="rounded-xl border border-border bg-card/50 backdrop-blur p-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground mb-3">
        <Activity className="w-4 h-4" />
        <span>近期活动</span>
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 py-2 animate-pulse">
              <div className="w-2.5 h-2.5 rounded-full bg-muted" />
              <div className="flex-1 space-y-1.5">
                <div className="h-3 bg-muted rounded w-3/4" />
                <div className="h-2.5 bg-muted rounded w-1/3" />
              </div>
            </div>
          ))}
        </div>
      ) : tasks.length === 0 ? (
        <div className="text-sm text-muted-foreground py-4 text-center">暂无活动记录</div>
      ) : (
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="show"
          className="space-y-0.5"
        >
          {tasks.map((task) => (
            <motion.div
              key={task.task_id}
              variants={itemVariants}
              className="flex items-center gap-3 py-2 px-2 rounded-lg hover:bg-muted/50 transition-colors"
            >
              <StatusDot
                status={STATUS_DOT_MAP[task.status] || 'idle'}
                size="sm"
              />
              <div className="flex-1 min-w-0">
                <div className="text-sm truncate">{task.problem_text || task.task_id}</div>
                <div className="text-xs text-muted-foreground">
                  {STATUS_LABELS[task.status] || task.status}
                  {task.created_at && (
                    <span className="ml-2">{formatTime(task.created_at)}</span>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  )
}
