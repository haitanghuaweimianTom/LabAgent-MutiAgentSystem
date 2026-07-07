'use client'

import { LucideIcon, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'

interface StatCardProps {
  icon: LucideIcon
  label: string
  value: string | number
  trend?: 'up' | 'down' | 'neutral'
  className?: string
}

const trendConfig = {
  up: { icon: TrendingUp, color: 'text-emerald-400' },
  down: { icon: TrendingDown, color: 'text-red-400' },
  neutral: { icon: Minus, color: 'text-slate-400' },
}

export function StatCard({ icon: Icon, label, value, trend = 'neutral', className }: StatCardProps) {
  const TrendIcon = trendConfig[trend].icon

  return (
    <div className={cn(
      'rounded-xl border border-border bg-card/50 backdrop-blur p-4',
      'transition-shadow duration-300 hover:shadow-glow',
      className
    )}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-muted-foreground text-sm">
          <Icon className="w-4 h-4" />
          <span>{label}</span>
        </div>
        <TrendIcon className={cn('w-3.5 h-3.5', trendConfig[trend].color)} />
      </div>
      <div className="text-2xl font-bold tracking-tight">{value}</div>
    </div>
  )
}
