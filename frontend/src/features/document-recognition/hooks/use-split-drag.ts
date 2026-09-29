/** 分屏左栏宽度拖拽：默认 52%，范围 32–70%，localStorage 记忆（vitest 覆盖纯逻辑部分）。 */

import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'

import { DEFAULT_SPLIT_PCT, MAX_SPLIT_PCT, MIN_SPLIT_PCT, SPLIT_PCT_KEY } from '../constants'

const clamp = (pct: number) => Math.min(MAX_SPLIT_PCT, Math.max(MIN_SPLIT_PCT, pct))

/** 初始宽度：localStorage 记忆值合法则沿用，否则默认（可注入 storage 便于单测） */
export function initialSplitPct(storage: Pick<Storage, 'getItem'> | undefined = typeof localStorage === 'undefined' ? undefined : localStorage): number {
  const saved = Number(storage?.getItem(SPLIT_PCT_KEY))
  return saved >= MIN_SPLIT_PCT && saved <= MAX_SPLIT_PCT ? saved : DEFAULT_SPLIT_PCT
}

/**
 * 分屏拖拽 hook：返回 [宽度%, 开始拖拽, 容器 ref, 是否拖拽中]。
 * 拖拽期间全局改列光标/禁选中，并对容器内 iframe 事件穿透做规避由调用方
 * 用 dragging 标记配合 pointer-events-none 处理。
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
      setPct(clamp(((e.clientX - rect.left) / rect.width) * 100))
    }
    const onUp = () => {
      setDragging(false)
      setPct((p) => {
        localStorage.setItem(SPLIT_PCT_KEY, String(Math.round(p)))
        return p
      })
    }
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
  }, [dragging])

  const startDrag = useCallback(() => {
    setDragging(true)
  }, [])

  return [pct, startDrag, bodyRef, dragging]
}
