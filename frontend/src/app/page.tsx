'use client'

import { useState, useEffect } from 'react'
import { ClipboardList, PlayCircle, CheckCircle2, XCircle } from 'lucide-react'
import { StatCard } from './components/StatCard'
import { ActivityTimeline } from './components/ActivityTimeline'
import SystemStatus from './components/SystemStatusClient'
import { apiBase } from '@/lib/api'

interface TaskInfo {
  status: string
}

export default function DashboardPage() {
  const [taskCounts, setTaskCounts] = useState({ total: 0, running: 0, completed: 0, failed: 0 })

  useEffect(() => {
    let cancelled = false
    async function fetchCounts() {
      try {
        const res = await fetch(apiBase() + '/tasks')
        const data: TaskInfo[] = await res.json()
        if (!cancelled) {
          setTaskCounts({
            total: data.length,
            running: data.filter(t => ['running', 'phase1', 'phase2'].includes(t.status)).length,
            completed: data.filter(t => t.status === 'completed').length,
            failed: data.filter(t => ['failed', 'cancelled'].includes(t.status)).length,
          })
        }
      } catch {}
    }
    fetchCounts()
    const interval = setInterval(fetchCounts, 15000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  return (
    <div className="p-6 space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={ClipboardList} label="Total Tasks" value={taskCounts.total} />
        <StatCard icon={PlayCircle} label="Running" value={taskCounts.running} trend={taskCounts.running > 0 ? 'up' : 'neutral'} />
        <StatCard icon={CheckCircle2} label="Completed" value={taskCounts.completed} trend={taskCounts.completed > 0 ? 'up' : 'neutral'} />
        <StatCard icon={XCircle} label="Failed" value={taskCounts.failed} trend={taskCounts.failed > 0 ? 'down' : 'neutral'} />
      </div>

      <ActivityTimeline />

      <SystemStatus />
    </div>
  )
}
