'use client'

// 扫描 [data-design-id] 可编辑元素，维护 hovered/selected，elementsFromPoint 命中。
// 只在 edit 模式激活。永不全量存 rect——rect 由 overlay 按需 getBoundingClientRect。

import { useState, useCallback } from 'react'
import { useDesignStore } from './store'
import type { EditableElement } from './types'

export function isExcluded(el: HTMLElement | null): boolean {
  return !!el?.closest('[data-design-exclude]')
}

function describe(target: HTMLElement): EditableElement | null {
  const id = target.getAttribute('data-design-id')
  if (!id) return null
  const parent = target.parentElement
  const groupId = parent?.hasAttribute('data-design-id') ? parent.getAttribute('data-design-id') : null
  return { id, el: target, groupId }
}

export function useEditableElements(active: boolean) {
  const selectedId = useDesignStore((s) => s.selectedId)
  const select = useDesignStore((s) => s.select)
  const [count, setCount] = useState(0)

  const rebuild = useCallback(() => {
    if (typeof document === 'undefined') return
    const nodes = document.querySelectorAll<HTMLElement>('[data-design-id]')
    let n = 0
    nodes.forEach((el) => {
      if (!isExcluded(el)) n++
    })
    setCount(n)
  }, [])

  const hoverAt = useCallback((x: number, y: number): EditableElement | null => {
    if (typeof document === 'undefined') return null
    const stack = document.elementsFromPoint(x, y)
    for (const node of stack) {
      const target = (node as HTMLElement).closest<HTMLElement>('[data-design-id]')
      if (target && !isExcluded(target)) {
        return describe(target)
      }
    }
    return null
  }, [])

  return { count, rebuild, hoverAt, selectedId, select, isExcluded }
}
