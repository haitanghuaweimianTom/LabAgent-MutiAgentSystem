'use client'

import { useState, useEffect, useCallback } from 'react'

type Theme = 'dark' | 'light'

export function useTheme() {
  const [theme, setTheme] = useState<Theme>('light')

  useEffect(() => {
    // layout.tsx 的内联脚本已在 hydrate 前设好 class；此处同步 React 状态。
    const saved = localStorage.getItem('theme') as Theme | null
    const current = saved === 'dark' || saved === 'light' ? saved : 'light'
    setTheme(current)
    document.documentElement.classList.remove('dark', 'light')
    document.documentElement.classList.add(current)
  }, [])

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark'
      localStorage.setItem('theme', next)
      document.documentElement.classList.remove('dark', 'light')
      document.documentElement.classList.add(next)
      return next
    })
  }, [])

  return { theme, toggleTheme }
}
