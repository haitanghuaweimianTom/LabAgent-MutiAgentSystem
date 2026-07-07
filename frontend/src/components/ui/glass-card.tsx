'use client'

import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'

interface GlassCardProps {
  children: React.ReactNode
  className?: string
  hover?: boolean
  onClick?: () => void
}

export function GlassCard({ children, className, hover = true, onClick }: GlassCardProps) {
  return (
    <motion.div
      whileHover={hover ? { scale: 1.005 } : undefined}
      className={cn(
        'rounded-2xl border border-border bg-card backdrop-blur-xl p-6',
        'transition-shadow duration-300',
        hover && 'cursor-pointer hover:shadow-glow-lg',
        className
      )}
      onClick={onClick}
    >
      {children}
    </motion.div>
  )
}
