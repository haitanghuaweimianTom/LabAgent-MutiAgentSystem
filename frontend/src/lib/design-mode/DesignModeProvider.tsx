'use client'

// 设计模式 Provider：包住整个 client-layout 三段式布局，在末尾渲染 overlay。
// 重放 overrides 不受 mode 限制：view 模式（正常浏览）也要显示已保存的设计，
// 否则"只有进设计模式才看到"——违背"定死"初衷。

import { useEffect } from 'react'
import { usePathname } from 'next/navigation'
import { DesignOverlay } from './DesignOverlay'
import { applyOverrides } from './applyOverrides'
import { useDesignStore } from './store'

export function DesignModeProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()

  // mount 时从文件真相（.design-overrides.json）同步到 store，覆盖 localStorage 旧缓存。
  // 文件是唯一真相：Claude 清盘/写回源码后文件变了，浏览器也要跟着变，否则旧的固定宽度覆盖回不来。
  useEffect(() => {
    let cancelled = false
    fetch('/api/design')
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return
        useDesignStore.getState().loadPersisted(data)
        applyOverrides()
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  // route 变化后（等 AnimatePresence exit + mount）重放已保存的 overrides。
  // 这是持久设计的体现：不管在不在设计模式，已拖好的尺寸/顺序都生效。
  useEffect(() => {
    const t = setTimeout(() => applyOverrides(), 200)
    return () => clearTimeout(t)
  }, [pathname])

  return (
    <>
      {children}
      <DesignOverlay />
    </>
  )
}
