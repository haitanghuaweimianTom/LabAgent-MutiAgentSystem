'use client'

import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { TEAM_COLORS, TEAM_LABELS, TEAM_ICONS } from '@/lib/constants'
import { cn } from '@/lib/utils'
import {
  Users, Search, Database, BarChart3, Box, Code2, TrendingUp,
  Cpu, PenTool, CheckCircle2, FlaskConical, Palette, ListTodo,
  Lightbulb, FileText
} from 'lucide-react'

const ICON_MAP: Record<string, React.ComponentType<any>> = {
  Users, Search, Database, BarChart3, Box, Code2, TrendingUp,
  Cpu, PenTool, CheckCircle2, FlaskConical, Palette, ListTodo,
  Lightbulb, FileText,
}

interface AgentNode {
  id: string
  label: string
  icon: string
  color: string
  status: 'idle' | 'running' | 'completed' | 'failed'
  x: number
  y: number
}

interface Edge {
  from: string
  to: string
}

const AGENT_FLOW: string[][] = [
  ['coordinator'],
  ['requirement_decomposer'],
  ['analyzer_agent'],
  ['data_agent', 'research_agent'],
  ['innovation_agent'],
  ['modeler_agent', 'algorithm_engineer_agent', 'financial_analyst_agent'],
  ['solver_agent'],
  ['experimentation_agent'],
  ['figure_agent'],
  ['writer_agent'],
  ['peer_review_agent'],
  ['summary_agent'],
]

const EDGES: Edge[] = [
  { from: 'coordinator', to: 'requirement_decomposer' },
  { from: 'requirement_decomposer', to: 'analyzer_agent' },
  { from: 'analyzer_agent', to: 'data_agent' },
  { from: 'analyzer_agent', to: 'research_agent' },
  { from: 'data_agent', to: 'innovation_agent' },
  { from: 'research_agent', to: 'innovation_agent' },
  { from: 'innovation_agent', to: 'modeler_agent' },
  { from: 'innovation_agent', to: 'algorithm_engineer_agent' },
  { from: 'innovation_agent', to: 'financial_analyst_agent' },
  { from: 'modeler_agent', to: 'solver_agent' },
  { from: 'algorithm_engineer_agent', to: 'solver_agent' },
  { from: 'financial_analyst_agent', to: 'solver_agent' },
  { from: 'solver_agent', to: 'experimentation_agent' },
  { from: 'experimentation_agent', to: 'figure_agent' },
  { from: 'figure_agent', to: 'writer_agent' },
  { from: 'writer_agent', to: 'peer_review_agent' },
  { from: 'peer_review_agent', to: 'summary_agent' },
]

function buildNodes(activeAgent?: string, completedAgents?: Set<string>): AgentNode[] {
  const nodes: AgentNode[] = []
  const nodeW = 140
  const nodeH = 44
  const gapX = 180
  const gapY = 56
  const startY = 30

  AGENT_FLOW.forEach((row, rowIdx) => {
    const rowWidth = row.length * nodeW + (row.length - 1) * 20
    const startX = (600 - rowWidth) / 2

    row.forEach((agentId, colIdx) => {
      let status: AgentNode['status'] = 'idle'
      if (activeAgent === agentId) {
        status = 'running'
      } else if (completedAgents?.has(agentId)) {
        status = 'completed'
      } else if (activeAgent) {
        const activeRowIdx = AGENT_FLOW.findIndex((r) => r.includes(activeAgent))
        if (rowIdx < activeRowIdx) status = 'completed'
      }

      nodes.push({
        id: agentId,
        label: TEAM_LABELS[agentId] || agentId,
        icon: TEAM_ICONS[agentId] || 'Box',
        color: TEAM_COLORS[agentId] || '#64748B',
        status,
        x: startX + colIdx * (nodeW + 20),
        y: startY + rowIdx * (nodeH + gapY),
      })
    })
  })

  return nodes
}

interface AgentTopologyProps {
  activeAgent?: string
  completedAgents?: Set<string>
  className?: string
}

export default function AgentTopology({ activeAgent, completedAgents, className }: AgentTopologyProps) {
  const nodes = useMemo(() => buildNodes(activeAgent, completedAgents), [activeAgent, completedAgents])
  const nodeMap = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])

  return (
    <div className={cn('rounded-xl border border-border bg-card/50 backdrop-blur p-4 overflow-x-auto', className)}>
      <h3 className="text-sm font-semibold text-foreground mb-3">Agent 执行拓扑</h3>
      <svg viewBox="0 0 600 720" className="w-full max-w-[600px] mx-auto">
        <defs>
          {/* 渐变定义 */}
          {Object.entries(TEAM_COLORS).map(([id, color]) => (
            <linearGradient key={id} id={`grad-${id}`} x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor={color} stopOpacity={0.8} />
              <stop offset="100%" stopColor={color} stopOpacity={0.4} />
            </linearGradient>
          ))}
          {/* 发光效果 */}
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* 边（连线） */}
        {EDGES.map((edge, i) => {
          const from = nodeMap.get(edge.from)
          const to = nodeMap.get(edge.to)
          if (!from || !to) return null

          const x1 = from.x + 70
          const y1 = from.y + 44
          const x2 = to.x + 70
          const y2 = to.y

          // 判断边是否激活（源节点已完成或运行中）
          const isActive = from.status === 'completed' || from.status === 'running'

          return (
            <g key={i}>
              {/* 底线 */}
              <line
                x1={x1} y1={y1} x2={x2} y2={y2}
                stroke={isActive ? `${from.color}40` : 'rgba(148,163,184,0.15)'}
                strokeWidth={isActive ? 2 : 1}
                strokeDasharray={isActive ? '0' : '4 4'}
              />
              {/* 激活时的流动粒子 */}
              {isActive && from.status === 'running' && (
                <circle r={3} fill={from.color} filter="url(#glow)">
                  <animateMotion
                    dur="2s"
                    repeatCount="indefinite"
                    path={`M${x1},${y1} L${x2},${y2}`}
                  />
                  <animate
                    attributeName="opacity"
                    values="0.8;0.3;0.8"
                    dur="2s"
                    repeatCount="indefinite"
                  />
                </circle>
              )}
            </g>
          )
        })}

        {/* 节点 */}
        {nodes.map((node, idx) => {
          const IconComponent = ICON_MAP[node.icon] || Box
          const isRunning = node.status === 'running'
          const isCompleted = node.status === 'completed'

          return (
            <motion.g
              key={node.id}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: idx * 0.03, duration: 0.3 }}
            >
              {/* 外框（运行中发光） */}
              <rect
                x={node.x - 1}
                y={node.y - 1}
                width={142}
                height={46}
                rx={10}
                fill="none"
                stroke={isRunning ? node.color : 'transparent'}
                strokeWidth={isRunning ? 2 : 0}
                filter={isRunning ? 'url(#glow)' : undefined}
                opacity={isRunning ? 1 : 0}
              />
              {/* 背景 */}
              <rect
                x={node.x}
                y={node.y}
                width={140}
                height={44}
                rx={9}
                fill={isRunning
                  ? `url(#grad-${node.id})`
                  : isCompleted
                    ? `${node.color}15`
                    : 'rgba(30,41,59,0.6)'}
                stroke={isRunning ? node.color : isCompleted ? `${node.color}30` : 'rgba(148,163,184,0.15)'}
                strokeWidth={isRunning ? 1.5 : 1}
              />
              {/* 状态圆点 */}
              <circle
                cx={node.x + 16}
                cy={node.y + 22}
                r={5}
                fill={isRunning ? node.color : isCompleted ? '#22c55e' : '#475569'}
              />
              {/* 运行中脉冲 */}
              {isRunning && (
                <circle
                  cx={node.x + 16}
                  cy={node.y + 22}
                  r={5}
                  fill="none"
                  stroke={node.color}
                  strokeWidth={1.5}
                  opacity={0.6}
                >
                  <animate attributeName="r" from="5" to="14" dur="1.5s" repeatCount="indefinite" />
                  <animate attributeName="opacity" from="0.6" to="0" dur="1.5s" repeatCount="indefinite" />
                </circle>
              )}
              {/* 图标（用文字代替，SVG 内嵌 Lucide 图标太复杂） */}
              <text
                x={node.x + 30}
                y={node.y + 26}
                fill={isRunning ? '#F8FAFC' : isCompleted ? '#CBD5E1' : '#64748B'}
                fontSize={12}
                fontFamily="Inter, Noto Sans SC, sans-serif"
                fontWeight={isRunning ? 600 : 400}
              >
                {node.label}
              </text>
            </motion.g>
          )
        })}
      </svg>
    </div>
  )
}
