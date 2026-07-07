'use client'

import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Terminal, ChevronDown, ChevronUp } from 'lucide-react'
import { apiBase } from '@/lib/api'
import { cn } from '@/lib/utils'

interface LogEntry {
  id: number
  timestamp: string
  level: 'info' | 'warn' | 'error' | 'debug'
  agent?: string
  message: string
}

interface LogStreamProps {
  taskId: string
  className?: string
}

export default function LogStream({ taskId, className }: LogStreamProps) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [expanded, setExpanded] = useState(true)
  const [autoScroll, setAutoScroll] = useState(true)
  const containerRef = useRef<HTMLDivElement>(null)
  const logIdRef = useRef(0)

  useEffect(() => {
    if (!taskId) return

    const es = new EventSource(apiBase() + '/tasks/' + taskId + '/stream')
    const poll = setInterval(async () => {
      try {
        const res = await fetch(apiBase() + '/tasks/' + taskId + '/messages?limit=50')
        if (res.ok) {
          const msgs = await res.json()
          const newLogs: LogEntry[] = msgs
            .filter((m: any) => m.type === 'system' || m.type === 'log')
            .slice(-30)
            .map((m: any) => ({
              id: logIdRef.current++,
              timestamp: m.timestamp,
              level: m.type === 'error' ? 'error' : m.type === 'warn' ? 'warn' : 'info',
              agent: m.sender,
              message: m.content,
            }))
          setLogs((prev) => {
            const prevIds = new Set(prev.map((l) => l.message + l.timestamp))
            const fresh = newLogs.filter((l) => !prevIds.has(l.message + l.timestamp))
            return fresh.length > 0 ? [...prev.slice(-49), ...fresh] : prev
          })
        }
      } catch {}
    }, 2000)

    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data)
        if (d.current_step) {
          setLogs((prev) => [
            ...prev.slice(-49),
            {
              id: logIdRef.current++,
              timestamp: new Date().toISOString(),
              level: 'info',
              message: d.current_step,
            },
          ])
        }
      } catch {}
    }

    es.onerror = () => es.close()
    return () => {
      es.close()
      clearInterval(poll)
    }
  }, [taskId])

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const levelColor = (level: string) => {
    switch (level) {
      case 'error': return 'text-error'
      case 'warn': return 'text-warning'
      case 'debug': return 'text-muted-foreground'
      default: return 'text-foreground/80'
    }
  }

  return (
    <div className={cn('rounded-xl border border-border bg-card/50 backdrop-blur overflow-hidden', className)}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-muted/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">实时日志</span>
          <span className="text-xs text-muted-foreground">({logs.length})</span>
        </div>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        )}
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 'auto' }}
            exit={{ height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div
              ref={containerRef}
              className="h-[240px] overflow-y-auto px-4 pb-3 font-mono text-xs space-y-0.5"
            >
              {logs.length === 0 && (
                <div className="text-muted-foreground py-8 text-center">等待日志...</div>
              )}
              {logs.map((log) => (
                <div key={log.id} className="flex gap-2 py-0.5 leading-5">
                  <span className="text-muted-foreground/60 shrink-0 w-[70px]">
                    {new Date(log.timestamp).toLocaleTimeString('zh-CN', { hour12: false })}
                  </span>
                  {log.agent && (
                    <span className="text-primary/70 shrink-0">{log.agent}</span>
                  )}
                  <span className={levelColor(log.level)}>{log.message}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between px-4 py-1.5 border-t border-border">
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoScroll}
                  onChange={(e) => setAutoScroll(e.target.checked)}
                  className="rounded border-border"
                />
                自动滚动
              </label>
              <button
                onClick={() => setLogs([])}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                清空
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
