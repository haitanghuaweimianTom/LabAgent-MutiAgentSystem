import { cn } from '@/lib/utils'

type Status = 'running' | 'completed' | 'failed' | 'pending' | 'idle'

interface StatusDotProps {
  status: Status
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sizeMap = {
  sm: 'w-2 h-2',
  md: 'w-2.5 h-2.5',
  lg: 'w-3 h-3',
}

const colorMap: Record<Status, string> = {
  running: 'status-dot-running',
  completed: 'status-dot-completed',
  failed: 'status-dot-failed',
  pending: 'status-dot-pending',
  idle: 'status-dot-idle',
}

export function StatusDot({ status, size = 'md', className }: StatusDotProps) {
  return (
    <span className={cn('status-dot', sizeMap[size], colorMap[status], className)} />
  )
}
