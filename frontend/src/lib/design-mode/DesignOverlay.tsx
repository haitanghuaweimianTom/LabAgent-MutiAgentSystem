'use client'

// 全局可视化设计模式 overlay。
// portal 到 document.body、z-[60]、根层 pointer-events:none（手柄/move grip 按需开 auto）。
// 用全局 document 事件（capture 阶段）做 hover/select，不铺 capture 层——这样 exclude 区
// （侧栏/顶栏/详情/开关）的事件自然放行，业务可正常工作；打标元素被拦截=选中。
// 永不全量存 rect：只对 selected+hovered 按需 getBoundingClientRect，rAF 合并重算。

import { createPortal } from 'react-dom'
import { useEffect, useState, useRef, useCallback } from 'react'
import { usePathname } from 'next/navigation'
import { GripHorizontal } from 'lucide-react'
import { useDesignStore } from './store'
import { useEditableElements } from './useEditableElements'
import { applyOverrides, findEl } from './applyOverrides'

type Handle = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'

const HANDLES: Handle[] = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

const CURSOR: Record<Handle, string> = {
  n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize',
  ne: 'nesw-resize', sw: 'nesw-resize', nw: 'nwse-resize', se: 'nwse-resize',
}

function cssEsc(s: string): string {
  if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') return CSS.escape(s)
  return s.replace(/["\\]/g, '\\$&')
}

function sameRect(a: DOMRect | null, b: DOMRect | null): boolean {
  if (!a || !b) return a === b
  return a.left === b.left && a.top === b.top && a.width === b.width && a.height === b.height
}

function handleStyle(h: Handle, r: DOMRect): React.CSSProperties {
  const s: React.CSSProperties = { position: 'fixed', pointerEvents: 'auto', width: 12, height: 12 }
  const cx = r.left + r.width / 2
  const cy = r.top + r.height / 2
  if (h.includes('n')) s.top = r.top - 6
  else if (h.includes('s')) s.top = r.bottom - 6
  else s.top = cy - 6
  if (h.includes('w')) s.left = r.left - 6
  else if (h.includes('e')) s.left = r.right - 6
  else s.left = cx - 6
  return s
}

function boxStyle(r: DOMRect): React.CSSProperties {
  return { position: 'fixed', left: r.left, top: r.top, width: r.width, height: r.height, pointerEvents: 'none' }
}

export function DesignOverlay() {
  const mode = useDesignStore((s) => s.mode)
  const [mounted, setMounted] = useState(false)
  useEffect(() => { setMounted(true) }, [])
  const active = mounted && mode === 'edit'

  const { count, rebuild, hoverAt, selectedId, select, isExcluded } = useEditableElements(active)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [selRect, setSelRect] = useState<DOMRect | null>(null)
  const [hovRect, setHovRect] = useState<DOMRect | null>(null)
  const [insertAt, setInsertAt] = useState<{ rect: DOMRect; horizontal: boolean } | null>(null)
  const pathname = usePathname()

  // route 变化 / active 切换 → 等 AnimatePresence exit(0.15s)+mount 后重建描述符 + 重放覆盖
  useEffect(() => {
    if (!active) return
    const t = setTimeout(() => { rebuild(); applyOverrides() }, 200)
    return () => clearTimeout(t)
  }, [pathname, active, rebuild])

  // edit 模式：html 加 .design-editing → 全局 user-select:none + 禁原生 drag（CSS 根治拖动复制）
  useEffect(() => {
    if (typeof document === 'undefined') return
    document.documentElement.classList.toggle('design-editing', active)
    return () => document.documentElement.classList.remove('design-editing')
  }, [active])

  const updateRects = useCallback(() => {
    const selEl = selectedId ? findEl(selectedId) : null
    const sr = selEl && !isExcluded(selEl) ? selEl.getBoundingClientRect() : null
    setSelRect((prev) => (sameRect(prev, sr) ? prev : sr))
    const hovEl = hoveredId ? findEl(hoveredId) : null
    const hr = hovEl && !isExcluded(hovEl) ? hovEl.getBoundingClientRect() : null
    setHovRect((prev) => (sameRect(prev, hr) ? prev : hr))
  }, [selectedId, hoveredId, isExcluded])

  const rafRef = useRef<number | undefined>(undefined)
  const scheduleUpdate = useCallback(() => {
    if (rafRef.current != null) return
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = undefined
      updateRects()
    })
  }, [updateRects])

  // ResizeObserver(main + selected) + scroll/resize → rAF 重算（只算 2 个 rect）
  useEffect(() => {
    if (!active) return
    updateRects()
    const ro = new ResizeObserver(() => scheduleUpdate())
    const main = document.querySelector('main')
    if (main) ro.observe(main)
    const selEl = selectedId ? findEl(selectedId) : null
    if (selEl) ro.observe(selEl)
    const onScroll = () => scheduleUpdate()
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', onScroll)
    return () => {
      ro.disconnect()
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', onScroll)
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    }
  }, [active, selectedId, scheduleUpdate, updateRects])

  // reorder 内核：在父 flex 容器内用 CSS order 重排，up 后持久化 order 数组。
  // grip 直调（无阈值）；onDown 命中元素后经 beginDragWatch 阈值检测再调（点=选中，拖=重排）。
  const runReorder = useCallback((elId: string) => {
    const el = findEl(elId)
    const parent = el?.parentElement
    if (!el || !parent) return
    const sibs = Array.from(parent.children).filter(
      (c): c is HTMLElement => (c as HTMLElement).hasAttribute('data-design-id'),
    )
    if (sibs.length < 2) return // 父容器内只有自己一个可重排元素，不动
    const groupId = parent.getAttribute('data-design-id') // 父须有 id 才能持久化
    const horizontal = getComputedStyle(parent).flexDirection !== 'column'
    const rects = sibs.map((s) => ({ id: s.getAttribute('data-design-id')!, r: s.getBoundingClientRect() }))
    const setGroupOrder = useDesignStore.getState().setGroupOrder

    const move = (ev: PointerEvent) => {
      let idx = sibs.length
      for (let i = 0; i < rects.length; i++) {
        const mid = horizontal ? rects[i].r.left + rects[i].r.width / 2 : rects[i].r.top + rects[i].r.height / 2
        const p = horizontal ? ev.clientX : ev.clientY
        if (p < mid) { idx = i; break }
      }
      const without = rects.map((x) => x.id).filter((x) => x !== elId)
      without.splice(idx, 0, elId)
      without.forEach((sid, i) => {
        const node = parent.querySelector<HTMLElement>(`[data-design-id="${cssEsc(sid)}"]`)
        if (node) node.style.order = String(i)
      })
      // 插入线：idx>=length 画在末项之后，否则画在第 idx 项之前
      const isEnd = idx >= rects.length
      const anchor = isEnd ? rects[rects.length - 1].r : rects[idx].r
      const lineRect = isEnd
        ? (horizontal ? new DOMRect(anchor.right, anchor.top, 0, anchor.height) : new DOMRect(anchor.left, anchor.bottom, anchor.width, 0))
        : (horizontal ? new DOMRect(anchor.left, anchor.top, 0, anchor.height) : new DOMRect(anchor.left, anchor.top, anchor.width, 0))
      setInsertAt({ rect: lineRect, horizontal })
      scheduleUpdate()
    }
    const up = () => {
      document.removeEventListener('pointermove', move)
      document.removeEventListener('pointerup', up)
      setInsertAt(null)
      if (groupId) {
        const finalOrder = sibs
          .map((s) => s.getAttribute('data-design-id')!)
          .sort((a, b) => {
            const ea = parent.querySelector<HTMLElement>(`[data-design-id="${cssEsc(a)}"]`)
            const eb = parent.querySelector<HTMLElement>(`[data-design-id="${cssEsc(b)}"]`)
            return (Number(ea?.style.order) || 0) - (Number(eb?.style.order) || 0)
          })
        setGroupOrder(groupId, finalOrder)
      }
    }
    document.addEventListener('pointermove', move)
    document.addEventListener('pointerup', up)
  }, [scheduleUpdate])

  // 点中元素后挂一个阈值监听：移动 < 4px 视为"点击=选中"；超过 4px 才启动重排。
  // 避免"一点就拖"误触，同时让元素本体可拖动重排（不必非得抓 grip）。
  const beginDragWatch = useCallback((downEv: PointerEvent, elId: string) => {
    const sx = downEv.clientX
    const sy = downEv.clientY
    let started = false
    const onMove = (ev: PointerEvent) => {
      if (started) return
      if (Math.abs(ev.clientX - sx) > 4 || Math.abs(ev.clientY - sy) > 4) {
        started = true
        cleanup()
        runReorder(elId)
      }
    }
    const onUp = () => cleanup()
    const cleanup = () => {
      document.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerup', onUp)
    }
    document.addEventListener('pointermove', onMove)
    document.addEventListener('pointerup', onUp)
  }, [runReorder])

  // move grip：直接重排（无阈值，grip 就是重排意图）
  const startReorder = useCallback((e: React.PointerEvent) => {
    e.stopPropagation()
    if (!selectedId) return
    runReorder(selectedId)
  }, [selectedId, runReorder])

  // 全局 hover（pointermove，passive，不阻止业务）
  useEffect(() => {
    if (!active) return
    const onMove = (e: PointerEvent) => {
      const hit = hoverAt(e.clientX, e.clientY)
      setHoveredId(hit ? hit.id : null)
      scheduleUpdate()
    }
    document.addEventListener('pointermove', onMove, { passive: true })
    return () => document.removeEventListener('pointermove', onMove)
  }, [active, hoverAt, scheduleUpdate])

  // edit 模式：彻底禁用原生 drag + 文本选择，杜绝拖动元素时"复制文字/触发搜索/拖出 input"。
  // CSS（html.design-editing user-select:none）已根治选词；此处 JS 做三重保险，并阻止 input 的 mousedown 选词。
  useEffect(() => {
    if (!active) return
    const inEditable = (t: EventTarget | null) => {
      const el = t as HTMLElement | null
      return !!el?.closest('[data-design-id]')
    }
    // 阻止所有原生拖拽（input/link/img/选中文本拖出）
    const stopDrag = (e: Event) => e.preventDefault()
    // 打标元素的 mousedown：阻止 input 进入选词态（mousedown 是选词起点，pointerdown preventDefault 挡不住 input）
    const stopMouse = (e: MouseEvent) => {
      if (inEditable(e.target)) {
        e.preventDefault()
      }
    }
    // 选词兜底（CSS 已挡，双保险）
    const stopSelect = (e: Event) => {
      if (inEditable(e.target)) e.preventDefault()
    }
    document.addEventListener('dragstart', stopDrag, true)
    document.addEventListener('mousedown', stopMouse, true)
    document.addEventListener('selectstart', stopSelect, true)
    return () => {
      document.removeEventListener('dragstart', stopDrag, true)
      document.removeEventListener('mousedown', stopMouse, true)
      document.removeEventListener('selectstart', stopSelect, true)
    }
  }, [active])

  // 全局 click → select（capture 阶段；handle/move/exclude 放行）
  useEffect(() => {
    if (!active) return
    const onDown = (e: PointerEvent) => {
      const target = e.target as HTMLElement
      if (target.closest('[data-design-handle]')) return // resize 手柄，放行
      if (target.closest('[data-design-move]')) return // move grip，放行
      const hit = hoverAt(e.clientX, e.clientY)
      if (hit) {
        e.stopPropagation()
        e.preventDefault()
        select(hit.id)
        scheduleUpdate()
        // 点中元素 → 先选中；若拖动超过 4px 则启动行内重排（拖本体重排）
        beginDragWatch(e, hit.id)
      } else if (!isExcluded(target)) {
        select(null) // 点空白（非 exclude）取消选中
      }
      // exclude 区（侧栏/顶栏/详情/开关）→ 放行，业务正常
    }
    document.addEventListener('pointerdown', onDown, true)
    return () => document.removeEventListener('pointerdown', onDown, true)
  }, [active, hoverAt, select, scheduleUpdate, isExcluded, beginDragWatch])

  // resize：拖角/边改 inline width/height（绝不碰 fontSize），up 后提交 store
  const startResize = useCallback((e: React.PointerEvent, h: Handle) => {
    e.stopPropagation()
    if (!selectedId) return
    const el = findEl(selectedId)
    if (!el) return
    const start = el.getBoundingClientRect()
    const px = e.clientX
    const py = e.clientY
    const setSize = useDesignStore.getState().setSize
    // flex-1 / flex-grow 元素（如 URL 输入框撑满行）设 inline width 会被 flex 覆盖。
    // 拖宽前先解除撑满（flex:none + 明确 width），resize 才生效。横向拖动同理。
    const cs = getComputedStyle(el)
    const isFlexGrow = (cs.flexGrow !== '0' && cs.flexGrow !== '') || el.classList.contains('flex-1')
    if (isFlexGrow && (h.includes('e') || h.includes('w'))) {
      el.style.flex = 'none'
      el.style.width = start.width + 'px'
    }
    // block 元素（如纯文本标题 div，display:block + width:auto 撑满父）：拖水平时左端被父起始锁死，
    // 只能从一端改。转成 inline-block（宽度独立于父）后两端都能自由拖。
    const isBlock = cs.display === 'block'
    if (isBlock && (h.includes('e') || h.includes('w'))) {
      el.style.display = 'inline-block'
      el.style.width = start.width + 'px'
    }
    // block/flex 元素高度由内容决定：拖垂直时设明确 height 才生效（否则 height:auto 被内容撑）。
    if ((isBlock || cs.display.includes('flex')) && (h.includes('n') || h.includes('s'))) {
      el.style.height = start.height + 'px'
    }
    const move = (ev: PointerEvent) => {
      const dx = ev.clientX - px
      const dy = ev.clientY - py
      let w = start.width
      let hg = start.height
      if (h.includes('e')) w = start.width + dx
      if (h.includes('w')) w = start.width - dx
      if (h.includes('s')) hg = start.height + dy
      if (h.includes('n')) hg = start.height - dy
      w = Math.max(24, Math.round(w))
      hg = Math.max(20, Math.round(hg))
      el.style.width = w + 'px'
      el.style.height = hg + 'px'
      scheduleUpdate()
    }
    const up = () => {
      document.removeEventListener('pointermove', move)
      document.removeEventListener('pointerup', up)
      const r = el.getBoundingClientRect()
      setSize(selectedId, { width: Math.round(r.width), height: Math.round(r.height) })
    }
    document.addEventListener('pointermove', move)
    document.addEventListener('pointerup', up)
  }, [selectedId, scheduleUpdate])


  if (!active) return null

  const moveGripStyle: React.CSSProperties | null = selRect
    ? { position: 'fixed', left: selRect.left + selRect.width / 2 - 12, top: selRect.top - 28, pointerEvents: 'auto' }
    : null

  return createPortal(
    <div className="fixed inset-0 z-[60]" style={{ pointerEvents: 'none' }}>
      {hovRect && hoveredId && hoveredId !== selectedId && (
        <div className="absolute border-2 border-warning/60 rounded-sm" style={boxStyle(hovRect)} />
      )}
      {selRect && selectedId && (
        <>
          <div className="absolute border-2 border-primary rounded-sm" style={boxStyle(selRect)} />
          {moveGripStyle && (
            <div
              data-design-move=""
              onPointerDown={startReorder}
              className="absolute flex items-center justify-center w-6 h-6 rounded-md bg-card border border-border shadow-[var(--shadow-glow-lg)] cursor-grab active:cursor-grabbing"
              style={moveGripStyle}
              title="拖动重排"
            >
              <GripHorizontal className="w-3.5 h-3.5 text-muted-foreground" />
            </div>
          )}
          {HANDLES.map((h) => (
            <div
              key={h}
              data-design-handle=""
              onPointerDown={(e) => startResize(e, h)}
              className="absolute bg-background border-2 border-primary rounded-sm"
              style={{ cursor: CURSOR[h], ...handleStyle(h, selRect) }}
            />
          ))}
        </>
      )}
      {insertAt && <InsertLine rect={insertAt.rect} horizontal={insertAt.horizontal} />}

      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-3 rounded-full border border-border bg-card px-5 py-2 text-sm shadow-[var(--shadow-glow-lg)]" style={{ pointerEvents: 'none' }}>
        <span className="h-2 w-2 rounded-full bg-warning" />
        <span className="font-medium text-foreground">设计模式</span>
        <span className="text-muted-foreground">{count > 0 ? `${count} 个可编辑元素 · 拖角改大小 · 拖顶部 grip 重排 · 点元素选中` : '未检测到可编辑元素（此页面未打标）'}</span>
      </div>
    </div>,
    document.body,
  )
}

function InsertLine({ rect, horizontal }: { rect: DOMRect; horizontal: boolean }) {
  const style: React.CSSProperties = horizontal
    ? { position: 'fixed', left: rect.left - 1, top: rect.top, width: 2, height: rect.height }
    : { position: 'fixed', left: rect.left, top: rect.top - 1, width: rect.width, height: 2 }
  return <div className="pointer-events-none absolute bg-primary" style={style} />
}
