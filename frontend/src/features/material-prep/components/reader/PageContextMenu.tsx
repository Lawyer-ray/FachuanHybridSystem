import { useCallback, useEffect, useRef } from 'react'
import { Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'

/** 页面上右键弹出的上下文菜单 */
export function PageContextMenu({
  x,
  y,
  title,
  count,
  onDelete,
  onClose,
}: {
  x: number
  y: number
  title: string
  count: number
  onDelete: () => void
  onClose: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  // 用 ref 存最新 onClose，"点外部关闭"订阅只挂一次（onClose 每次渲染常是新引用）。
  // 写 ref 放 effect 里，不放 render 主体（React 19 react-hooks/refs 规则）
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])
  const handleClose = useCallback(() => onCloseRef.current(), [])

  // 定位要贴近右键点，同时别被画布边缘裁掉：改用 fixed，超界时夹回视口内
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const { innerWidth: vw, innerHeight: vh } = window
    const { offsetWidth: w, offsetHeight: h } = el
    let left = x
    let top = y
    if (left + w > vw - 8) left = Math.max(8, vw - w - 8)
    if (top + h > vh - 8) top = Math.max(8, vh - h - 8)
    el.style.left = `${left}px`
    el.style.top = `${top}px`
  }, [x, y])

  // 点击菜单外部或按 Esc 关闭
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) handleClose()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose()
    }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    window.addEventListener('blur', handleClose)
    return () => {
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('blur', handleClose)
    }
  }, [handleClose])

  return (
    <div
      ref={ref}
      className="fixed z-[90] min-w-[160px] overflow-hidden rounded-lg border border-border bg-card py-1 text-[13px] shadow-2xl"
      onContextMenu={(e) => e.preventDefault()}
    >
      <div className="px-3 py-1.5 text-[11px] text-muted-foreground">{title}</div>
      <button
        type="button"
        onClick={onDelete}
        className={cn(
          'flex w-full items-center gap-2 px-3 py-2 text-left text-destructive transition-colors hover:bg-destructive/10',
        )}
      >
        <Trash2 className="h-3.5 w-3.5" />
        {count > 1 ? `删除所选 ${count} 页` : '删除此页'}
      </button>
    </div>
  )
}
