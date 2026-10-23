/**
 * 详情页 AI 工作区的宽度拖拽：默认 640px，钳制在 [480, 容器-40]。
 * 工作区是**第一列**，把手在其右缘（向右拖变宽）。宽度超过
 * 「容器 - 756」（案件卡 320 + 档案栏 400 + gap 36 的最小占位）后进入
 * 聚焦模式：其余两列整列隐藏、工作区独占整行（DealDetailPage 按
 * 宽度阈值渲染，这里只管宽度本身）。拖动中直改 grid 容器上的
 * `--deal-ai-w` CSS 变量（ref + 直接 DOM，高频 pointermove 不触发整页
 * 重渲染），松手才提交 state 并持久化 localStorage——与 copilot 浮层的
 * use-panel-resize 同一模式，此处归 workbench（列宽是详情页布局的私事）。
 */

import { useCallback, useRef, useState } from 'react'

const WIDTH_KEY = 'deal:ai-width'
const FOCUS_KEY = 'deal:ai-focus'
const MIN_WIDTH = 480
/** 其余两列（案件卡 320 + 档案栏 400 + gap 36）的最小占位 */
export const REST_MIN = 756
const DEFAULT_WIDTH = 640

/** 钳制：下限保住工作区自身可读，上限留 40px 边距（聚焦模式由拖动阈值切换） */
function clampWidth(px: number, avail: number): number {
  const max = Math.max(MIN_WIDTH, avail - 40)
  return Math.round(Math.min(max, Math.max(MIN_WIDTH, px)))
}

function readStoredFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
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
  /** 聚焦模式：用户**拖动**越过共存阈值（容器-REST_MIN）才进入/退出——
   *  记忆宽度在窄容器被钳制后只收窄显示，不会凭空触发聚焦（否则默认
   *  640 在小容器上直接满屏，三列形态再也回不来） */
  const [focus, setFocus] = useState(() => readStoredFlag(FOCUS_KEY))
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

  /** 工作区右缘把手（面板锚定左侧，向右拖变宽） */
  const onHandlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return
      e.preventDefault()
      drag.current = { startX: e.clientX, startWidth: width }
      document.body.style.userSelect = 'none'
      let lastFocus: boolean | null = null
      const onMove = (ev: PointerEvent) => {
        const state = drag.current
        if (!state) return
        const avail = gridRef.current?.offsetWidth ?? window.innerWidth
        const next = clampWidth(state.startWidth + (ev.clientX - state.startX), avail)
        // 拖动中直改 CSS 变量：不触发 React 重渲染
        gridRef.current?.style.setProperty('--deal-ai-w', `${next}px`)
        state.targetWidth = next
        // 跨过共存阈值才切聚焦（状态翻转时才 set，拖动本身不逐帧重渲染）
        const nowFocus = next > avail - REST_MIN
        if (nowFocus !== lastFocus) {
          lastFocus = nowFocus
          setFocus(nowFocus)
        }
      }
      const onUp = () => {
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
        document.body.style.userSelect = ''
        const target = drag.current?.targetWidth
        const targetFocus = lastFocus ?? focus
        drag.current = null
        if (typeof target === 'number' && target !== width) {
          setWidth(target)
          try {
            localStorage.setItem(WIDTH_KEY, String(target))
          } catch {
            /* 忽略持久化失败 */
          }
        }
        try {
          localStorage.setItem(FOCUS_KEY, targetFocus ? '1' : '0')
        } catch {
          /* 忽略持久化失败 */
        }
      }
      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onUp)
    },
    [width, focus],
  )

  return { width, focus, setGridRef, onHandlePointerDown }
}
