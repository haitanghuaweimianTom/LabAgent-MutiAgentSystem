'use client'

import { motion } from 'framer-motion'
import { TEAM_COLORS, TEAM_LABELS } from '@/lib/constants'
import { cn } from '@/lib/utils'

interface AgentNode {
  id: string
  label: string
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
  ['modeler_agent', 'algorithm_engineer_agent'],
  ['solver_agent'],
  ['experimentation_agent'],
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
  { from: 'modeler_agent', to: 'solver_agent' },
  { from: 'algorithm_engineer_agent', to: 'solver_agent' },
  { from: 'solver_agent', to: 'experimentation_agent' },
  { from: 'experimentation_agent', to: 'writer_agent' },
  { from: 'writer_agent', to: 'peer_review_agent' },
  { from: 'peer_review_agent', to: 'summary_agent' },
]

function buildNodes(activeAgent?: string): AgentNode[] {
  const nodes: AgentNode[] = []
  const nodeW = 140
  const nodeH = 36
  const gapX = 180
  const gapY = 50
  const startY = 30

  AGENT_FLOW.forEach((row, rowIdx) => {
    const rowWidth = row.length * nodeW + (row.length - 1) * 20
    const startX = (600 - rowWidth) / 2

    row.forEach((agentId, colIdx) => {
      const status =
        activeAgent === agentId
          ? 'running'
          : rowIdx < AGENT_FLOW.findIndex((r) => r.includes(activeAgent || ''))
            ? 'completed'
            : 'idle'

      nodes.push({
        id: agentId,
        label: TEAM_LABELS[agentId] || agentId,
        status: activeAgent ? status : 'idle',
        x: startX + colIdx * (nodeW + 20),
        y: startY + rowIdx * (nodeH + gapY),
      })
    })
  })

  return nodes
}

interface AgentTopologyProps {
  activeAgent?: string
  className?: string
}

export default function AgentTopology({ activeAgent, className }: AgentTopologyProps) {
  const nodes = buildNodes(activeAgent)
  const nodeMap = new Map(nodes.map((n) => [n.id, n]))

  const statusColor = (status: string) => {
    switch (status) {
      case 'running': return 'from-primary to-secondary'
      case 'completed': return 'from-success/80 to-success/60'
      case 'failed': return 'from-error/80 to-error/60'
      default: return 'from-muted to-muted'
    }
  }

  const statusBorder = (status: string) => {
    switch (status) {
      case 'running': return 'border-primary/50 shadow-[0_0_12px_rgba(59,130,246,0.3)]'
      case 'completed': return 'border-success/50'
      case 'failed': return 'border-error/50'
      default: return 'border-border'
    }
  }

  return (
    <div className={cn('rounded-xl border border-border bg-card/50 backdrop-blur p-4 overflow-x-auto', className)}>
      <h3 className="text-sm font-semibold text-foreground mb-3">Agent 执行拓扑</h3>
      <svg viewBox="0 0 600 520" className="w-full max-w-[600px] mx-auto">
        {/* Edges */}
        {EDGES.map((edge, i) => {
          const from = nodeMap.get(edge.from)
          const to = nodeMap.get(edge.to)
          if (!from || !to) return null
          const x1 = from.x + 70
          const y1 = from.y + 36
          const x2 = to.x + 70
          const y2 = to.y
          return (
            <line
              key={i}
              x1={x1} y1={y1} x2={x2} y2={y2}
              stroke="rgba(148,163,184,0.2)"
              strokeWidth={1.5}
              strokeDasharray={activeAgent ? '0' : '4 4'}
            />
          )
        })}

        {/* Nodes */}
        {nodes.map((node) => (
          <g key={node.id}>
            <rect
              x={node.x}
              y={node.y}
              width={140}
              height={36}
              rx={8}
              fill="none"
              stroke={node.status === 'running' ? TEAM_COLORS[node.id] || '#3B82F6' : 'rgba(148,163,184,0.2)'}
              strokeWidth={node.status === 'running' ? 2 : 1}
              className={node.status === 'running' ? 'drop-shadow-[0_0_8px_rgba(59,130,246,0.4)]' : ''}
            />
            <rect
              x={node.x + 1}
              y={node.y + 1}
              width={138}
              height={34}
              rx={7}
              fill={node.status === 'running' ? `${TEAM_COLORS[node.id]}15` : node.status === 'completed' ? 'rgba(34,197,94,0.08)' : 'rgba(30,41,59,0.6)'}
            />
            <circle
              cx={node.x + 14}
              cy={node.y + 18}
              r={4}
              fill={node.status === 'running' ? TEAM_COLORS[node.id] : node.status === 'completed' ? '#22c55e' : '#475569'}
            />
            {node.status === 'running' && (
              <circle
                cx={node.x + 14}
                cy={node.y + 18}
                r={4}
                fill="none"
                stroke={TEAM_COLORS[node.id]}
                strokeWidth={1}
                opacity={0.5}
              >
                <animate attributeName="r" from="4" to="10" dur="1.5s" repeatCount="indefinite" />
                <animate attributeName="opacity" from="0.5" to="0" dur="1.5s" repeatCount="indefinite" />
              </circle>
            )}
            <text
              x={node.x + 24}
              y={node.y + 22}
              fill={node.status === 'running' ? '#F8FAFC' : '#94A3B8'}
              fontSize={12}
              fontFamily="Inter, Noto Sans SC, sans-serif"
            >
              {node.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}
