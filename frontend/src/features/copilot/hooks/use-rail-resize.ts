/**
 * 会话侧栏宽度拖拽：右缘把手 col-resize，向右拖变宽。
 *
 * 为什么需要：侧栏固定 180px 时，委托名（委托方全称常有二三十字）与对话标题
 * 一律被截成（委托方全称被截断），隔着几个项目根本分不清。ZCode 侧栏
 * 可拖宽，这里对齐同一手感。
 *
 * 与 use-panel-resize 同模式：拖动中直改 rail 元素的 `--copilot-rail-w`
 * CSS 变量（高频 pointermove 不经 React 协调），松手才提交 state 并持久化
 * localStorage；宽度钳制在 [MIN, 面板宽 - 对话区最小宽度]，保证右侧对话区
 * 永远还剩可读宽度。监听与页面外壳同 use-panel-resize，交给 `beginDrag`。
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { beginDrag } from '@/lib/drag-listeners'

const RAIL_WIDTH_KEY = 'copilot:rail-width'
/** 下限=原固定宽度；上限靠面板宽度动态钳制 */
const MIN_WIDTH = 180
const DEFAULT_WIDTH = 220
/** 拖宽后右侧对话区至少要剩这么多，否则只看得见侧栏 */
const CHAT_MIN = 280

function readStoredWidth(): number {
  try {
    const raw = Number(localStorage.getItem(RAIL_WIDTH_KEY))
    return Number.isFinite(raw) && raw >= MIN_WIDTH ? Math.round(raw) : DEFAULT_WIDTH
  } catch {
    return DEFAULT_WIDTH
  }
}

interface RailResize {
  /** 当前侧栏宽度（px） */
  width: number
  /** 绑定到 rail 根节点的 ref（拖拽直改其 CSS 变量） */
  setRailRef: (node: HTMLElement | null) => void
  /** 绑定到右缘把手的 pointerdown */
  onHandlePointerDown: (e: React.PointerEvent) => void
}

/**
 * @param panelWidth 面板总宽（px），用于把侧栏上限钳制在「面板 - CHAT_MIN」
 */
export function useRailResize(panelWidth: number): RailResize {
  const [width, setWidth] = useState(readStoredWidth)
  const railRef = useRef<HTMLElement | null>(null)
  /** 卸载时它收尾正在进行的拖拽 */
  const endDragRef = useRef<(() => void) | null>(null)
  useEffect(() => () => endDragRef.current?.(), [])

  const clamp = useCallback(
    (px: number) => {
      // panelWidth 未知（0，如单测直接渲染侧栏）时不钳上限，否则会被压到
      // MIN_WIDTH，默认宽度失效
      if (panelWidth <= 0) return Math.round(Math.max(MIN_WIDTH, px))
      const max = Math.max(MIN_WIDTH, panelWidth - CHAT_MIN)
      return Math.round(Math.min(max, Math.max(MIN_WIDTH, px)))
    },
    [panelWidth],
  )

  const setRailRef = useCallback((node: HTMLElement | null) => {
    railRef.current = node
  }, [])

  const onHandlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return
      e.preventDefault()
      // 上一次拖拽若没收到收尾事件（极端情况），先把它结束了再开新的
      endDragRef.current?.()
      const startX = e.clientX
      const startWidth = clamp(width)
      let target = startWidth
      const onMove = (ev: MouseEvent) => {
        // 侧栏在左，向右拖变宽
        target = clamp(startWidth + (ev.clientX - startX))
        railRef.current?.style.setProperty('--copilot-rail-w', `${target}px`)
      }
      // 收尾：pointerup / pointercancel / 卸载都走这里。必须收 pointercancel，
      // 否则触摸设备被系统手势打断时页面永久停在 userSelect: none。
      endDragRef.current = beginDrag(
        onMove,
        () => {
          endDragRef.current = null
          if (target !== width) {
            setWidth(target)
            try {
              localStorage.setItem(RAIL_WIDTH_KEY, String(target))
            } catch {
              /* 忽略持久化失败 */
            }
          }
        },
        { blockIframes: true },
      )
    },
    [width, clamp],
  )

  return { width: clamp(width), setRailRef, onHandlePointerDown }
}
