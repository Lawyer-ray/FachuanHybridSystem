import { useCallback, useEffect, useRef } from 'react'
import type { InboxMessage } from '../types'

type JudgeFn = (pack: { id: number }, target: 'done' | 'filed') => void

/**
 * DeskPage 的网格键盘导航：←→ 移、↑↓ 换行、Space/Enter 打开、X 不接。
 * 仅在阅读器未打开（列表态）时生效，输入框内不劫持按键。
 */
export function useDeskKeyboard(params: {
  visible: InboxMessage[]
  openId: number | null
  sel: number
  setSel: React.Dispatch<React.SetStateAction<number>>
  openAt: (index: number) => void
  judge: JudgeFn
}) {
  const { visible, openId, sel, setSel, openAt, judge } = params
  const gridRef = useRef<HTMLDivElement | null>(null)

  // 计算当前网格列数（读 CSS grid-template-columns），↑↓ 按一行跨度跳
  const gridCols = useCallback(() => {
    const grid = gridRef.current
    if (!grid) return 1
    const tcs = getComputedStyle(grid).gridTemplateColumns
    return tcs.split(' ').length
  }, [])

  useEffect(() => {
    if (openId != null) return
    const onKey = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        (e.target as HTMLElement).closest?.('input, textarea, select')
      )
        return
      if (visible.length === 0) return
      const cols = gridCols()
      if (e.key === 'ArrowRight') {
        setSel((s) => Math.min(visible.length - 1, s + 1))
        e.preventDefault()
      } else if (e.key === 'ArrowLeft') {
        setSel((s) => Math.max(0, s - 1))
        e.preventDefault()
      } else if (e.key === 'ArrowDown') {
        setSel((s) => Math.min(visible.length - 1, s + (cols || 1)))
        e.preventDefault()
      } else if (e.key === 'ArrowUp') {
        setSel((s) => Math.max(0, s - (cols || 1)))
        e.preventDefault()
      } else if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        openAt(sel)
      } else if (e.key === 'x' || e.key === 'X') {
        const p = visible[sel]
        if (p) judge(p, 'filed')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, openId, sel, openAt, judge])

  return gridRef
}
