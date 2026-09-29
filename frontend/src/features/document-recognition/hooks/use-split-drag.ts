/** 分屏/弹窗宽度拖拽：范围约束 + localStorage 记忆。 */

import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'

import { DEFAULT_SPLIT_PCT, DIALOG_WIDTH_KEY, MAX_SPLIT_PCT, MIN_DIALOG_WIDTH, MIN_SPLIT_PCT, SPLIT_PCT_KEY } from '../constants'

const clampSplit = (pct: number) => Math.min(MAX_SPLIT_PCT, Math.max(MIN_SPLIT_PCT, pct))

/** 初始分屏宽度：localStorage 记忆值合法则沿用，否则默认（可注入 storage 便于单测） */
export function initialSplitPct(
  storage: Pick<Storage, 'getItem'> | undefined = typeof localStorage === 'undefined' ? undefined : localStorage,
): number {
  const saved = Number(storage?.getItem(SPLIT_PCT_KEY))
  return saved >= MIN_SPLIT_PCT && saved <= MAX_SPLIT_PCT ? saved : DEFAULT_SPLIT_PCT
}

/** 初始弹窗宽度（px）：无记忆或低于下限时返回 null（走 CSS 默认尺寸） */
export function initialDialogWidth(
  storage: Pick<Storage, 'getItem'> | undefined = typeof localStorage === 'undefined' ? undefined : localStorage,
): number | null {
  const saved = Number(storage?.getItem(DIALOG_WIDTH_KEY))
  return saved >= MIN_DIALOG_WIDTH ? saved : null
}

/** 拖拽基建：全局 mousemove/mouseup + body 列光标/禁选中，返回清理函数。 */
function attachDragListeners(onMove: (e: MouseEvent) => void, onUp: () => void): () => void {
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
  return () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
  }
}

/**
 * 分屏左栏宽度拖拽：返回 [宽度%, 开始拖拽, 容器 ref, 是否拖拽中]。
 * 拖拽中 iframe 事件穿透的规避由调用方用 dragging 标记配 pointer-events-none。
 */
export function useSplitDrag(): [number, () => void, RefObject<HTMLDivElement | null>, boolean] {
  const [pct, setPct] = useState(initialSplitPct)
  const [dragging, setDragging] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!dragging) return
    const onMove = (e: MouseEvent) => {
      const rect = bodyRef.current?.getBoundingClientRect()
      if (!rect || rect.width === 0) return
      setPct(clampSplit(((e.clientX - rect.left) / rect.width) * 100))
    }
    const onUp = () => {
      setDragging(false)
      setPct((p) => {
        localStorage.setItem(SPLIT_PCT_KEY, String(Math.round(p)))
        return p
      })
    }
    return attachDragListeners(onMove, onUp)
  }, [dragging])

  const startDrag = useCallback(() => {
    setDragging(true)
  }, [])

  return [pct, startDrag, bodyRef, dragging]
}

/** 弹窗整体宽度拖拽（px，右缘手柄向右拉变宽）：范围 [MIN_DIALOG_WIDTH, 视口-32px]，localStorage 记忆。
 *  默认 null = 走 CSS 自适应宽（min(95vw, 视口-48px)，接近网页边缘）——用户只需调小，不必先调大。
 *  返回的是「派生有效宽度」：存储的期望宽度不随窗口缩放被改写（反复拉宽变窄不丢），
 *  仅在渲染时钳到当前视口内。 */
export function useDialogWidthDrag(): [number | null, (e: { preventDefault: () => void; clientX: number; currentTarget: EventTarget & HTMLElement }) => void, boolean] {
  const [width, setWidth] = useState<number | null>(initialDialogWidth)
  const [dragging, setDragging] = useState(false)
  const [viewportW, setViewportW] = useState(() => window.innerWidth)
  const startRef = useRef({ x: 0, w: 0 })

  useEffect(() => {
    const onResize = () => setViewportW(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    if (!dragging) return
    const onMove = (e: MouseEvent) => {
      const maxW = window.innerWidth - 32
      setWidth(Math.min(maxW, Math.max(MIN_DIALOG_WIDTH, startRef.current.w + (e.clientX - startRef.current.x))))
    }
    const onUp = () => {
      setDragging(false)
      setWidth((w) => {
        if (w != null) localStorage.setItem(DIALOG_WIDTH_KEY, String(Math.round(w)))
        return w
      })
    }
    return attachDragListeners(onMove, onUp)
  }, [dragging])

  const startDrag = useCallback((e: { preventDefault: () => void; clientX: number; currentTarget: EventTarget & HTMLElement }) => {
    const dialog = e.currentTarget.closest('[role="dialog"]')
    startRef.current = { x: e.clientX, w: dialog?.getBoundingClientRect().width ?? MIN_DIALOG_WIDTH }
    e.preventDefault()
    setDragging(true)
  }, [])

  // 派生有效宽度：期望宽度只在渲染时钳到视口内，存储值不被窗口缩放破坏
  const effectiveWidth = width == null ? null : Math.min(width, Math.max(0, viewportW - 32))
  return [effectiveWidth, startDrag, dragging]
}
