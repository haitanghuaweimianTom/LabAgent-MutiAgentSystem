// 把 store 里的 entries (resize) / groups (reorder) 应用到 DOM。
// 调用时机：DesignModeProvider 首次 mount、route 变化后重建、store 数据变化。
// 只写 width/height/order，绝不碰 fontSize。

import { useDesignStore } from './store'

function cssEsc(s: string): string {
  if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') return CSS.escape(s)
  return s.replace(/["\\]/g, '\\$&')
}

export function findEl(id: string): HTMLElement | null {
  if (typeof document === 'undefined') return null
  return document.querySelector<HTMLElement>(`[data-design-id="${cssEsc(id)}"]`)
}

/** 应用所有覆盖到当前 DOM（仅对存在的元素生效，缺失的跳过）。 */
export function applyOverrides() {
  if (typeof document === 'undefined') return
  const { entries, groups } = useDesignStore.getState()

  for (const [id, size] of Object.entries(entries)) {
    const el = findEl(id)
    if (!el) continue
    // flex-1 / flex-grow 元素：设 width 前先解除撑满，否则被 flex 覆盖（resize 失效根因）
    if (size.width != null) {
      const cs = getComputedStyle(el)
      const isFlexGrow = (cs.flexGrow !== '0' && cs.flexGrow !== '') || el.classList.contains('flex-1')
      if (isFlexGrow) el.style.flex = 'none'
      el.style.width = size.width + 'px'
    }
    if (size.height != null) el.style.height = size.height + 'px'
  }

  for (const [groupId, g] of Object.entries(groups)) {
    const parent = findEl(groupId)
    if (!parent) continue
    g.order.forEach((id, i) => {
      const child = findEl(id)
      if (child) child.style.order = String(i)
    })
  }
}

/** 清除某元素的所有 inline 设计覆盖（写回源码后调用，恢复响应式）。 */
export function clearElInline(el: HTMLElement) {
  el.style.width = ''
  el.style.height = ''
  el.style.order = ''
}
