'use client'

import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Terminal, ChevronDown, ChevronUp, Trash2 } from 'lucide-react'
import { apiBase } from '@/lib/api'
import { TEAM_COLORS } from '@/lib/constants'
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
  const [filter, setFilter] = useState<'all' | 'agent' | 'error'>('all')
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
            return fresh.length > 0 ? [...prev.slice(-99), ...fresh] : prev
          })
        }
      } catch {}
    }, 2000)

    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data)
        if (d.current_step) {
          setLogs((prev) => [
            ...prev.slice(-99),
            {
              id: logIdRef.current++,
              timestamp: new Date().toISOString(),
              level: 'info',
              message: `[${d.current_step}]`,
            },
          ])
        }
        if (d.active_agent) {
          setLogs((prev) => [
            ...prev.slice(-99),
            {
              id: logIdRef.current++,
              timestamp: new Date().toISOString(),
              level: 'info',
              agent: d.active_agent,
              message: `开始执行`,
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

  const filteredLogs = logs.filter((log) => {
    if (filter === 'agent') return !!log.agent
    if (filter === 'error') return log.level === 'error' || log.level === 'warn'
    return true
  })

  const levelStyle = (level: string) => {
    switch (level) {
      case 'error': return 'text-red-400 bg-red-500/10'
      case 'warn': return 'text-amber-400 bg-amber-500/10'
      case 'debug': return 'text-slate-500'
      default: return 'text-slate-300'
    }
  }

  const agentColor = (agent?: string) => agent ? TEAM_COLORS[agent] || '#64748B' : '#64748B'

  return (
    <div className={cn('rounded-xl border border-border bg-card/50 backdrop-blur overflow-hidden', className)}>
      {/* 头部 */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-muted/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="relative">
            <Terminal className="w-4 h-4 text-muted-foreground" />
            {logs.some((l) => l.level === 'error') && (
              <span className="absolute -top-1 -right-1 w-2 h-2 bg-red-500 rounded-full" />
            )}
          </div>
          <span className="text-sm font-medium text-foreground">实时日志</span>
          <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
            {filteredLogs.length}
          </span>
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
            {/* 过滤器 */}
            <div className="flex items-center gap-1 px-4 py-1.5 border-b border-border">
              {(['all', 'agent', 'error'] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={cn(
                    'px-2 py-0.5 text-xs rounded transition-colors',
                    filter === f
                      ? 'bg-primary/20 text-primary'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                  )}
                >
                  {f === 'all' ? '全部' : f === 'agent' ? 'Agent' : '错误'}
                </button>
              ))}
            </div>

            {/* 日志内容 */}
            <div
              ref={containerRef}
              className="h-[280px] overflow-y-auto px-4 py-2 font-mono text-xs"
            >
              {filteredLogs.length === 0 && (
                <div className="text-muted-foreground py-12 text-center">
                  <Terminal className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  <p>等待日志...</p>
                </div>
              )}
              <AnimatePresence initial={false}>
                {filteredLogs.map((log) => (
                  <motion.div
                    key={log.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.15 }}
                    className={cn(
                      'flex items-start gap-2 py-1 px-2 rounded mb-0.5',
                      log.level === 'error' && 'bg-red-500/5',
                      log.level === 'warn' && 'bg-amber-500/5'
                    )}
                  >
                    <span className="text-slate-600 shrink-0 w-[56px] tabular-nums">
                      {new Date(log.timestamp).toLocaleTimeString('zh-CN', { hour12: false })}
                    </span>
                    {log.agent ? (
                      <span
                        className="shrink-0 px-1.5 py-0 rounded text-[10px] font-medium"
                        style={{
                          backgroundColor: `${agentColor(log.agent)}20`,
                          color: agentColor(log.agent),
                        }}
                      >
                        {log.agent}
                      </span>
                    ) : (
                      <span className="shrink-0 px-1.5 py-0 rounded text-[10px] text-slate-600 bg-slate-500/10">
                        sys
                      </span>
                    )}
                    <span className={cn('break-words', levelStyle(log.level))}>
                      {log.message}
                    </span>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>

            {/* 底部控制 */}
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
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                <Trash2 className="w-3 h-3" />
                清空
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
