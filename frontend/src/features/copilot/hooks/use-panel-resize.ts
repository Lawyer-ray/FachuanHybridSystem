/**
 * 面板宽度拖拽调整：左缘把手 col-resize，向左拖变宽（面板锚定右侧）。
 *
 * 拖动期间直改 aside 上的 `--copilot-w` CSS 变量（ref + 直接 DOM，高频
 * pointermove 不走 React 协调，避免整树重渲染卡顿）；松手才提交 state
 * 并持久化 localStorage，下次展开沿用。宽度钳制在 [min, 可用宽度]。
 *
 * 宽度同时镜像到 <html> 的 `--copilot-w-app`：AppShell 的并排模式用它给
 * 主内容区让出 padding-right（面板在壳层懒挂载，挂载即同步；拖动中同步
 * 保证让位与面板变宽同帧，松手提交 state 后由 effect 兜底）。
 */

import { useCallback, useEffect, useRef, useState } from 'react'

const WIDTH_KEY = 'copilot:width'
const MIN_WIDTH = 420
const RAIL_NEEDS = 560
const APP_VAR = '--copilot-w-app'

function syncAppVar(px: number): void {
  document.documentElement.style.setProperty(APP_VAR, `${px}px`)
}

function clampWidth(px: number): number {
  const max = Math.max(MIN_WIDTH, window.innerWidth - 320)
  return Math.round(Math.min(max, Math.max(MIN_WIDTH, px)))
}

function readStoredWidth(): number {
  try {
    const raw = Number(localStorage.getItem(WIDTH_KEY))
    return Number.isFinite(raw) && raw > 0 ? clampWidth(raw) : 600
  } catch {
    return 600
  }
}

interface PanelResize {
  /** 受控宽度（px），sm 以上生效 */
  width: number
  /** 该宽度是否容得下常驻会话栏 */
  railCapable: boolean
  /** 绑定到 aside 的 ref（拖拽直改它的 CSS 变量） */
  setPanelRef: (node: HTMLElement | null) => void
  /** 绑定到左缘把手的 pointerdown */
  onHandlePointerDown: (e: React.PointerEvent) => void
  minRailWidth: number
}

export function usePanelResize(isSmUp: boolean): PanelResize {
  const [width, setWidth] = useState(readStoredWidth)
  const panelRef = useRef<HTMLElement | null>(null)

  const drag = useRef<{ startX: number; startWidth: number; targetWidth?: number } | null>(null)

  // 挂载与宽度提交时同步到 <html>（拖动中的高频同步在 onMove 里直改）
  useEffect(() => {
    syncAppVar(width)
  }, [width])

  const setPanelRef = useCallback((node: HTMLElement | null) => {
    panelRef.current = node
  }, [])

  const onHandlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return
      e.preventDefault()
      drag.current = { startX: e.clientX, startWidth: width }
      document.body.style.userSelect = 'none'
      const onMove = (ev: PointerEvent) => {
        const state = drag.current
        if (!state) return
        const next = clampWidth(state.startWidth + (state.startX - ev.clientX))
        // 拖动中直改 CSS 变量：不触发 React 重渲染
        panelRef.current?.style.setProperty('--copilot-w', `${next}px`)
        syncAppVar(next)
        // 松手前先本地记住目标值（up 时可能拿不到中间态）
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

  return {
    width,
    railCapable: isSmUp && width >= RAIL_NEEDS,
    setPanelRef,
    onHandlePointerDown,
    minRailWidth: RAIL_NEEDS,
  }
}
