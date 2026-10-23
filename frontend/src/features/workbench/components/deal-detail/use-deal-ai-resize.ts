/**
 * 详情页 AI 工作区的宽度拖拽：默认 640px，钳制在 [480, 视口-820]
 * （下限保住工作区自身可读，上限保住左列案件卡 + 400px 委托档案栏的
 * 最小可读宽）。拖动中直改 grid 容器上的 `--deal-ai-w` CSS 变量
 * （ref + 直接 DOM，高频 pointermove 不触发整页重渲染），松手才提交
 * state 并持久化 localStorage——与 copilot 浮层的 use-panel-resize
 * 同一模式，此处归 workbench（列宽是详情页布局的私事）。
 */

import { useCallback, useRef, useState } from 'react'

const WIDTH_KEY = 'deal:ai-width'
const MIN_WIDTH = 480
/** 容器里留给工作区之外的部分：左列案件卡 320 + 档案栏 400 + gap 36 */
const FLOOR_FOR_REST = 756
const DEFAULT_WIDTH = 640

function clampWidth(px: number, avail: number): number {
  const max = Math.max(MIN_WIDTH, avail - FLOOR_FOR_REST)
  return Math.round(Math.min(max, Math.max(MIN_WIDTH, px)))
}

/** 首渲染前容器未挂载，用视口近似；挂载后 setGridRef 再按容器实际宽收窄 */
function readStoredWidth(): number {
  try {
    const raw = Number(localStorage.getItem(WIDTH_KEY))
    return Number.isFinite(raw) && raw > 0 ? clampWidth(raw, window.innerWidth) : DEFAULT_WIDTH
  } catch {
    return DEFAULT_WIDTH
  }
}

export function useDealAiResize() {
  const [width, setWidth] = useState(readStoredWidth)
  const gridRef = useRef<HTMLElement | null>(null)
  const drag = useRef<{ startX: number; startWidth: number; targetWidth?: number } | null>(null)

  const setGridRef = useCallback(
    (node: HTMLElement | null) => {
      gridRef.current = node
      // 主容器有 max-w 断点（1280/1760/2200…），容器常比视口窄：记忆宽度
      // 在更大的屏存下后，换小容器渲染时收窄到不溢出为止
      if (node) {
        const capped = clampWidth(width, node.offsetWidth)
        if (capped !== width) setWidth(capped)
      }
    },
    [width],
  )

  /** 工作区左缘把手（面板锚定右侧，向左拖变宽） */
  const onHandlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return
      e.preventDefault()
      drag.current = { startX: e.clientX, startWidth: width }
      document.body.style.userSelect = 'none'
      const onMove = (ev: PointerEvent) => {
        const state = drag.current
        if (!state) return
        const avail = gridRef.current?.offsetWidth ?? window.innerWidth
        const next = clampWidth(state.startWidth + (state.startX - ev.clientX), avail)
        // 拖动中直改 CSS 变量：不触发 React 重渲染
        gridRef.current?.style.setProperty('--deal-ai-w', `${next}px`)
        state.targetWidth = next
      }
      const onUp = () => {
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
        document.body.style.userSelect = ''
        const target = drag.current?.targetWidth
        drag.current = null
        if (typeof target === 'number' && target !== width) {
          setWidth(target)
          try {
            localStorage.setItem(WIDTH_KEY, String(target))
          } catch {
            /* 忽略持久化失败 */
          }
        }
      }
      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onUp)
    },
    [width],
  )

  return { width, setGridRef, onHandlePointerDown }
}
