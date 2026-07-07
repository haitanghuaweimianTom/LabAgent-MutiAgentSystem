import { cn } from '@/lib/utils'

type AgentStatus = 'running' | 'completed' | 'failed' | 'pending' | 'idle'

interface AgentBadgeProps {
  name: string
  status: AgentStatus
  icon?: React.ReactNode
  className?: string
}

const statusColors: Record<AgentStatus, string> = {
  running: 'bg-primary/15 text-primary border-primary/30',
  completed: 'bg-success/15 text-success border-success/30',
  failed: 'bg-error/15 text-error border-error/30',
  pending: 'bg-warning/15 text-warning border-warning/30',
  idle: 'bg-muted text-muted-foreground border-border',
}

const dotColors: Record<AgentStatus, string> = {
  running: 'status-dot-running',
  completed: 'status-dot-completed',
  failed: 'status-dot-failed',
  pending: 'status-dot-pending',
  idle: 'status-dot-idle',
}

export function AgentBadge({ name, status, icon, className }: AgentBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium border',
        statusColors[status],
        className
      )}
    >
      <span className={cn('status-dot', dotColors[status])} />
      {icon && <span className="shrink-0">{icon}</span>}
      <span>{name}</span>
    </span>
  )
}
