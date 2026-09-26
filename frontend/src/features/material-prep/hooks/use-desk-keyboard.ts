import { useCallback, useEffect, useRef } from 'react'
import type { InboxMessage } from '../types'

type JudgeFn = (pack: { id: number }, target: 'done' | 'filed') => void

/**
 * DeskPage 的网格键盘导航：←→ 移、↑↓ 换行、Space/Enter 打开、X 不接。
 * 仅在阅读器未打开（列表态）时生效，输入框内不劫持按键。
 *
 * 内部用 ref 跟踪最新的 sel / visible / openAt / judge，监听只挂一次——
 * 否则每次 setSel、每次列表变化都会拆装 window 监听。
 * gridRef 由调用方（DeskPage）持有并真正 attach 到网格容器，供 ↑↓ 读列数。
 */
export function useDeskKeyboard(params: {
  visible: InboxMessage[]
  openId: number | null
  sel: number
  setSel: React.Dispatch<React.SetStateAction<number>>
  openAt: (index: number) => void
  judge: JudgeFn
  gridRef: React.RefObject<HTMLDivElement | null>
}) {
  const { visible, openId, sel, setSel, openAt, judge, gridRef } = params

  // 用 ref 保存最新值，让 keydown effect 不必因它们变化而重订阅。
  // 写 ref 放在 effect 里，不放在 render 主体（React 19 react-hooks/refs 规则）
  const latest = useRef({ visible, openId, sel, openAt, judge })
  useEffect(() => {
    latest.current = { visible, openId, sel, openAt, judge }
  }, [visible, openId, sel, openAt, judge])

  // 计算当前网格列数（读 CSS grid-template-columns），↑↓ 按一行跨度跳
  const gridCols = useCallback(() => {
    const grid = gridRef.current
    if (!grid) return 1
    const tcs = getComputedStyle(grid).gridTemplateColumns
    return tcs.split(' ').length
  }, [gridRef])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const { visible: vis, openId: opened, sel: idx, openAt: open, judge: j } = latest.current
      if (opened != null) return
      if (
        e.target instanceof HTMLInputElement ||
        (e.target as HTMLElement).closest?.('input, textarea, select')
      )
        return
      if (vis.length === 0) return
      const cols = gridCols()
      if (e.key === 'ArrowRight') {
        setSel((s) => Math.min(vis.length - 1, s + 1))
        e.preventDefault()
      } else if (e.key === 'ArrowLeft') {
        setSel((s) => Math.max(0, s - 1))
        e.preventDefault()
      } else if (e.key === 'ArrowDown') {
        setSel((s) => Math.min(vis.length - 1, s + (cols || 1)))
        e.preventDefault()
      } else if (e.key === 'ArrowUp') {
        setSel((s) => Math.max(0, s - (cols || 1)))
        e.preventDefault()
      } else if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        open(idx)
      } else if (e.key === 'x' || e.key === 'X') {
        const p = vis[idx]
        if (p) j(p, 'filed')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setSel, gridCols])
}
