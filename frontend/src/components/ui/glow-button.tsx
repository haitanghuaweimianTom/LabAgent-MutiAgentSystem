'use client'

import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'

interface GlowButtonProps {
  children: React.ReactNode
  className?: string
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  onClick?: () => void
}

const variantStyles = {
  primary: 'bg-gradient-to-r from-primary to-secondary text-white',
  secondary: 'bg-muted text-foreground border border-border',
  ghost: 'bg-transparent text-muted-foreground hover:text-foreground hover:bg-muted',
}

const sizeStyles = {
  sm: 'h-7 px-3 text-xs',
  md: 'h-9 px-4 text-sm',
  lg: 'h-11 px-6 text-base',
}

export function GlowButton({
  children,
  className,
  variant = 'primary',
  size = 'md',
  disabled,
  onClick,
}: GlowButtonProps) {
  return (
    <motion.button
      whileHover={!disabled ? { scale: 1.02, y: -1 } : undefined}
      whileTap={!disabled ? { scale: 0.98 } : undefined}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-lg font-medium',
        'transition-all duration-200 outline-none',
        'focus-visible:ring-2 focus-visible:ring-primary/50',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        variant === 'primary' && 'shadow-glow hover:shadow-glow-lg',
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </motion.button>
  )
}
