'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTaskState } from '@/app/hooks/useTaskState'
import { useAppStore } from '@/app/store/useAppStore'
import { apiBase } from '@/lib/api'
import { Message } from '@/lib/types'
import { TEAM_LABELS } from '@/lib/constants'
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
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data)
        setTaskStatus(d.status)
        setProgress(d.progress || 0)
        setCurrentStep(d.current_step || '')
        if (d.active_agent) setActiveAgent(d.active_agent)
        if (d.status === 'paused') { setPaused(true); es.close(); clearInterval(msgPoll); setActiveAgent(undefined) }
        if (d.status === 'phase1_completed') {
          const wf = d.workflow_type || ''
          if (wf === 'deep_research' || wf === 'research_survey') { autoConfirmSubProblems(id) }
          else { setPhase('phase2_confirm'); loadSubProblems(id) }
          es.close(); clearInterval(msgPoll)
        }
        if (['completed', 'failed', 'cancelled'].includes(d.status)) { es.close(); clearInterval(msgPoll); setActiveAgent(undefined) }
      } catch {}
    }
    es.onerror = () => { es.close(); clearInterval(msgPoll) }
  }, [eventSource])

  useEffect(() => {
    if (taskId) startSSE(taskId)
    return () => { if (eventSource) eventSource.close() }
  }, [taskId])

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
    <div className="p-6 space-y-4">
      {/* Phase Controls */}
      {(phase === 'idle' && taskId && taskStatus !== 'running' && taskStatus !== 'completed') && (
        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-primary font-semibold">分阶段工作流</span>
            <button
              onClick={handlePhase1}
              className="px-3 py-1.5 rounded-lg bg-primary/10 border border-primary/20 text-primary text-sm hover:bg-primary/20 transition-colors"
            >
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
                <input
                  value={sp}
                  onChange={e => { const next = [...subProblems]; next[idx] = e.target.value; setSubProblems(next) }}
                  className="flex-1 px-3 py-2 rounded-lg bg-muted border border-border text-foreground text-sm"
                />
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

      {/* Agent Topology */}
      {taskId && ['running', 'paused', 'phase1', 'phase2'].includes(taskStatus) && (
        <AgentTopology activeAgent={activeAgent} />
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

      {/* Log Stream */}
      {taskId && ['running', 'paused', 'phase1', 'phase2'].includes(taskStatus) && (
        <LogStream taskId={taskId} />
      )}

      {/* Message List */}
      {taskId && messages.length > 0 && (
        <div className="rounded-xl border border-border bg-card">
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
        <div className="sticky bottom-0 bg-background/95 backdrop-blur border-t border-border p-4">
          <div className="flex gap-2">
            <input
              type="text"
              value={newMessage}
              onChange={e => setNewMessage(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
              placeholder="输入消息与 Agent 交互..."
              className="flex-1 px-4 py-2.5 rounded-xl bg-muted border border-border text-foreground text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 transition-colors"
            />
            <button
              onClick={sendMessage}
              disabled={!newMessage.trim()}
              className="px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              发送
            </button>
          </div>
        </div>
      )}

      {/* Camera Ready */}
      {taskState.state?.name === 'completed' && taskId && (
        <CameraReadyPanel taskId={taskId} templateId={taskState.state?.templateId || 'math_modeling'} />
      )}
    </div>
  )
}
