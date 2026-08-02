'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTaskState } from '@/app/hooks/useTaskState'
import { useAppStore } from '@/app/store/useAppStore'
import { apiBase } from '@/lib/api'
import { Message } from '@/lib/types'
import { TEAM_LABELS, nodeLabel } from '@/lib/constants'
import { PreFlightPanel, PreflightReport } from '@/app/components/PreFlightPanel'
import { CameraReadyPanel } from '@/app/components/CameraReadyPanel'
import DiscussionPanel from '@/app/components/DiscussionPanel'
import AgentTopology from '@/app/components/AgentTopology'
import LogStream from '@/app/components/LogStream'

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
  const [activeAgent, setActiveAgent] = useState<string | undefined>()
  const [newMessage, setNewMessage] = useState('')

  const activeProjectId = useAppStore((s) => s.activeProjectId)

  useEffect(() => {
    if (taskState.state) {
      setTaskStatus(taskState.state.name)
      setProgress(taskState.state.progressPercentage)
      setCurrentStep(taskState.state.currentStep)
    }
  }, [taskState.state])

  useEffect(() => {
    if (paused && taskId) loadPauseData()
  }, [paused])

  const esRef = useRef<EventSource | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryCountRef = useRef(0)
  const intentionallyClosedRef = useRef(false)

  const closeSSE = useCallback(() => {
    intentionallyClosedRef.current = true
    if (reconnectTimerRef.current) { clearTimeout(reconnectTimerRef.current); reconnectTimerRef.current = null }
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    if (esRef.current) { esRef.current.close(); esRef.current = null }
    setEventSource(null)
  }, [])

  const startSSE = useCallback((id: string) => {
    if (esRef.current) { esRef.current.close(); esRef.current = null }
    if (reconnectTimerRef.current) { clearTimeout(reconnectTimerRef.current); reconnectTimerRef.current = null }
    retryCountRef.current = 0
    intentionallyClosedRef.current = false

    const es = new EventSource(apiBase() + '/tasks/' + id + '/stream')
    esRef.current = es
    setEventSource(es)

    if (!pollRef.current) {
      pollRef.current = setInterval(async () => {
        try {
          const res = await fetch(apiBase() + '/tasks/' + id + '/messages')
          if (res.ok) {
            const msgs = await res.json()
            const newMsgs = msgs.map((m: any) => ({
              id: m.id, sender: m.sender,
              sender_label: m.sender_label || TEAM_LABELS[m.sender] || m.sender,
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
    }

    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data)
        // 收到事件说明连接健康，重置重连退避计数
        retryCountRef.current = 0
        setTaskStatus(d.status)
        setProgress(d.progress || 0)
        setCurrentStep(d.current_step || '')
        if (d.active_agent) setActiveAgent(d.active_agent)
        if (d.status === 'paused') { setPaused(true); closeSSE(); setActiveAgent(undefined) }
        if (d.status === 'phase1_completed') {
          const wf = d.workflow_type || ''
          if (wf === 'deep_research' || wf === 'research_survey') { autoConfirmSubProblems(id) }
          else { setPhase('phase2_confirm'); loadSubProblems(id) }
          closeSSE()
        }
        if (['completed', 'failed', 'cancelled'].includes(d.status)) { closeSSE(); setActiveAgent(undefined) }
      } catch {}
    }
    es.onerror = () => {
      if (intentionallyClosedRef.current) return
      es.close()
      esRef.current = null
      // 指数退避重连（1s→2s→4s→…→封顶 30s），避免断网/后端重启后页面变僵尸
      const delay = Math.min(30000, 1000 * 2 ** retryCountRef.current)
      retryCountRef.current += 1
      reconnectTimerRef.current = setTimeout(() => { if (!intentionallyClosedRef.current) startSSE(id) }, delay)
    }
  }, [closeSSE])

  useEffect(() => {
    if (taskId) startSSE(taskId)
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      if (pollRef.current) clearInterval(pollRef.current)
      if (esRef.current) esRef.current.close()
      setEventSource(null)
    }
  }, [taskId, startSSE])

  const loadSubProblems = async (id: string) => {
    try {
      const res = await fetch(apiBase() + '/tasks/' + id + '/result')
      if (res.ok) {
        const data = await res.json()
        const sp = data?.output?.analyzer_agent?.sub_problems || data?.output?.sub_problems || []
        if (sp.length > 0) setSubProblems(sp.map((s: any) => s.description || s.text || s))
      }
    } catch {}
  }

  const handlePhase1 = async () => {
    if (!taskId) return
    setSubmitting(true)
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/phase1', { method: 'POST' })
      if (res.ok) { setPhase('phase1'); setTaskStatus('running'); startSSE(taskId) }
    } catch { alert('启动阶段1失败') } finally { setSubmitting(false) }
  }

  const handlePhase2 = async () => {
    if (!taskId || subProblems.length === 0) return
    setSubmitting(true)
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/phase2', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sub_problems: subProblems, mode: solveMode }),
      })
      if (res.ok) { setPhase('phase2'); setTaskStatus('running'); startSSE(taskId) }
    } catch { alert('启动阶段2失败') } finally { setSubmitting(false) }
  }

  const autoConfirmSubProblems = async (id: string) => {
    try {
      const res = await fetch(apiBase() + '/tasks/' + id + '/result')
      if (res.ok) {
        const data = await res.json()
        const sps = data.output?.analyzer_agent?.sub_problems || []
        if (sps.length > 0) {
          await fetch(apiBase() + '/tasks/' + id + '/confirm-subproblems', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sub_problems: sps }),
          })
          setPhase('phase2'); setTaskStatus('running'); startSSE(id)
        }
      }
    } catch {}
  }

  const handleConfirmSubproblems = async () => {
    if (!taskId) return
    setSubmitting(true)
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/confirm-subproblems', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sub_problems: subProblems }),
      })
      if (res.ok) { setPhase('phase2'); setTaskStatus('running'); startSSE(taskId) }
    } catch { alert('确认子问题失败') } finally { setSubmitting(false) }
  }

  const handlePause = async () => {
    if (!taskId) return
    try { await fetch(apiBase() + '/tasks/' + taskId + '/pause', { method: 'POST' }); setPaused(true) } catch {}
  }

  const handleResume = async () => {
    if (!taskId) return
    setResuming(true)
    try { await fetch(apiBase() + '/tasks/' + taskId + '/resume', { method: 'POST' }); setPaused(false); startSSE(taskId) } catch {} finally { setResuming(false) }
  }

  const handleCancel = async () => {
    if (!taskId) return
    if (!confirm('确定取消当前任务？')) return
    setCancelling(true)
    try {
      await fetch(apiBase() + '/tasks/' + taskId + '/cancel', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: '用户手动取消' }),
      })
      setTaskStatus('cancelled')
    } catch {} finally { setCancelling(false) }
  }

  const loadPauseData = async () => {
    if (!taskId) return
    try { const res = await fetch(apiBase() + '/tasks/' + taskId + '/pause-data'); if (res.ok) setPauseData(await res.json()) } catch {}
  }

  const sendMessage = async () => {
    if (!taskId || !newMessage.trim()) return
    const content = newMessage.trim()
    setNewMessage('')
    try {
      const res = await fetch(apiBase() + '/tasks/' + taskId + '/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, sender: 'user', type: 'text' }),
      })
      if (res.ok) {
        const msg = await res.json()
        setMessages(prev => [...prev, {
          id: msg.id, sender: 'user',
          sender_label: msg.sender_label || '用户',
          content, type: 'text', timestamp: msg.timestamp || new Date().toISOString(),
        }])
      }
    } catch {}
  }

  return (
    <div data-design-id="task:root" className="mx-auto w-full max-w-[1320px] p-6 space-y-4 flex flex-col items-center">
      {/* Phase Controls */}
      {(phase === 'idle' && taskId && taskStatus !== 'running' && taskStatus !== 'completed') && (
        <div data-design-id="task:card-phase" className="w-full rounded-xl border border-primary/20 bg-primary/5 p-4">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-primary font-semibold">分阶段工作流</span>
            <button
              onClick={handlePhase1}
              data-design-id="task:btn-phase1"
              className="inline-flex items-center justify-center gap-3 min-h-[40px] py-2 px-8 bg-primary text-primary-foreground rounded-lg text-sm cursor-pointer transition-opacity hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
            >
              启动阶段1（分析+数据）
            </button>
          </div>
          <p className="text-sm text-muted-foreground">阶段1完成后可确认子问题列表，再启动阶段2建模求解</p>
        </div>
      )}

      {/* Phase 2 Confirm */}
      {phase === 'phase2_confirm' && (
        <div data-design-id="task:card-phase2" className="w-full rounded-xl border border-success/20 bg-success/5 p-4">
          <span className="text-success font-semibold block mb-3">阶段1已完成 — 确认子问题后启动阶段2</span>
          <div data-design-id="task:row-subproblems" className="space-y-2 mb-4">
            {subProblems.map((sp, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <span className="text-warning text-sm w-5">{idx + 1}.</span>
                <input
                  value={sp}
                  onChange={e => { const next = [...subProblems]; next[idx] = e.target.value; setSubProblems(next) }}
                  className="flex-1 px-3 py-2 rounded-lg bg-muted border border-border text-foreground text-sm"
                />
                <button onClick={() => setSubProblems(subProblems.filter((_, i) => i !== idx))} className="px-2 py-1 rounded text-error text-xs hover:bg-error/10">✕</button>
              </div>
            ))}
            <button onClick={() => setSubProblems([...subProblems, ''])} data-design-id="task:btn-addsub" className="inline-flex items-center justify-center gap-2 min-h-[28px] py-1 px-3 bg-primary/10 text-primary border border-primary/20 rounded-lg text-xs cursor-pointer transition-colors hover:bg-primary/20 shrink-0">+ 添加子问题</button>
          </div>
          <div data-design-id="task:row-solvemode" className="flex items-center gap-4 mb-4">
            <span className="text-sm text-muted-foreground">求解策略：</span>
            <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
              <input type="radio" checked={solveMode === 'sequential'} onChange={() => setSolveMode('sequential')} /> 逐个递进
            </label>
            <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
              <input type="radio" checked={solveMode === 'batch'} onChange={() => setSolveMode('batch')} /> 批量并行
            </label>
          </div>
          <div className="flex gap-3 items-center flex-wrap">
            <button onClick={handleConfirmSubproblems} disabled={submitting} data-design-id="task:btn-phase2" className="btn-gradient">启动阶段2</button>
            <button onClick={() => { setPhase('idle'); setSubProblems([]) }} data-design-id="task:btn-cancel" className="inline-flex items-center justify-center gap-3 min-h-[40px] py-2 px-8 bg-primary/10 text-primary border border-primary/20 rounded-lg text-sm cursor-pointer transition-colors hover:bg-primary/20 shrink-0">取消</button>
          </div>
        </div>
      )}

      {/* Progress Bar */}
      {(taskStatus === 'running' || taskStatus === 'phase1' || taskStatus === 'phase2') && (
        <div data-design-id="task:row-progress" className="w-full space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{nodeLabel(currentStep) || '准备中...'}</span>
            <span className="text-primary font-medium">{Math.round(progress)}%</span>
          </div>
          <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
            <div className="h-full rounded-full bg-gradient-to-r from-primary to-secondary transition-all duration-500" style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}

      {/* Agent Topology */}
      {taskId && ['running', 'paused', 'phase1', 'phase2'].includes(taskStatus) && (
        <div data-design-id="task:card-topology" className="w-full"><AgentTopology activeAgent={activeAgent} /></div>
      )}

      {/* Control Buttons */}
      {taskId && taskStatus !== 'completed' && taskStatus !== 'cancelled' && (
        <div data-design-id="task:row-controls" className="flex gap-3 items-center flex-wrap w-full">
          {paused ? (
            <button onClick={handleResume} disabled={resuming} data-design-id="task:btn-resume" className="btn-gradient">{resuming ? '恢复中...' : '恢复'}</button>
          ) : (
            <button onClick={handlePause} data-design-id="task:btn-pause" className="inline-flex items-center justify-center gap-3 min-h-[40px] py-2 px-8 bg-primary/10 text-primary border border-primary/20 rounded-lg text-sm cursor-pointer transition-colors hover:bg-primary/20 shrink-0">暂停</button>
          )}
          <button onClick={handleCancel} disabled={cancelling} data-design-id="task:btn-cancel-task" className="inline-flex items-center justify-center gap-3 min-h-[36px] py-1.5 px-6 bg-error/10 text-error border border-error/20 rounded-md text-sm cursor-pointer transition-colors hover:bg-error/15 disabled:opacity-50 disabled:cursor-not-allowed shrink-0">
            {cancelling ? '取消中...' : '终止'}
          </button>
        </div>
      )}

      {/* Preflight Report */}
      {preflightReport && <div data-design-id="task:card-preflight" className="w-full"><PreFlightPanel report={preflightReport} /></div>}

      {/* Discussion Panel Toggle */}
      {taskId && (taskStatus === 'running' || taskStatus === 'paused') && (
        <button onClick={() => setShowDiscussion(!showDiscussion)} data-design-id="task:btn-discussion" className="inline-flex items-center justify-center gap-3 min-h-[40px] py-2 px-8 bg-primary/10 text-primary border border-primary/20 rounded-lg text-sm cursor-pointer transition-colors hover:bg-primary/20 shrink-0">
          {showDiscussion ? '关闭讨论面板' : 'Agent 讨论面板'}
        </button>
      )}

      {showDiscussion && taskId && <div data-design-id="task:card-discussion" className="w-full"><DiscussionPanel taskId={taskId} onClose={() => setShowDiscussion(false)} /></div>}

      {/* Log Stream */}
      {taskId && ['running', 'paused', 'phase1', 'phase2'].includes(taskStatus) && (
        <div data-design-id="task:card-logs" className="w-full"><LogStream taskId={taskId} /></div>
      )}

      {/* Message List */}
      {taskId && messages.length > 0 && (
        <div data-design-id="task:card-messages" className="w-full rounded-xl border border-border bg-card">
          <div className="px-4 py-3 border-b border-border">
            <span className="text-sm font-medium text-foreground">对话记录</span>
            <span className="text-xs text-muted-foreground ml-2">({messages.length})</span>
          </div>
          <div className="max-h-96 overflow-y-auto p-4 space-y-3">
            {messages.map((msg) => (
              <div key={msg.id} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] rounded-xl px-4 py-2.5 ${
                  msg.sender === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : msg.type === 'system'
                      ? 'bg-muted text-muted-foreground border border-border'
                      : 'bg-secondary/10 text-foreground border border-secondary/20'
                }`}>
                  <div className="text-xs mb-1 opacity-70">{msg.sender_label}</div>
                  <div className="text-sm whitespace-pre-wrap break-words">{msg.content}</div>
                  <div className="text-[10px] mt-1 opacity-50">{new Date(msg.timestamp).toLocaleTimeString()}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Chat Input */}
      {taskId && ['running', 'paused', 'phase1', 'phase2', 'completed'].includes(taskStatus) && (
        <div data-design-id="task:row-chat" className="w-full sticky bottom-0 bg-background/95 backdrop-blur border-t border-border p-4">
          <div className="flex gap-3 items-center flex-wrap">
            <input
              type="text"
              value={newMessage}
              onChange={e => setNewMessage(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
              placeholder="输入消息与 Agent 交互..."
              data-design-id="task:input-chat"
              className="flex-1 min-w-[280px] h-10 px-5 bg-muted border border-border rounded-lg text-foreground text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 placeholder:text-muted-foreground transition-colors"
            />
            <button
              onClick={sendMessage}
              disabled={!newMessage.trim()}
              data-design-id="task:btn-send"
              className="inline-flex items-center justify-center gap-3 min-h-[40px] py-2 px-8 bg-primary text-primary-foreground rounded-lg text-sm cursor-pointer transition-opacity hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
            >
              发送
            </button>
          </div>
        </div>
      )}

      {/* Camera Ready */}
      {taskState.state?.name === 'completed' && taskId && (
        <div data-design-id="task:card-camera" className="w-full"><CameraReadyPanel taskId={taskId} templateId={taskState.state?.templateId || 'math_modeling'} /></div>
      )}
    </div>
  )
}
