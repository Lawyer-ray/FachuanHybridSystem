import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

/**
 * 文件夹树的右键菜单与行内删除确认（与树的递归层拆开，满足单文件规模约束）。
 * 菜单用 portal + fixed：树常处在右栏 overflow 容器内，就地 absolute 会被裁掉。
 */

export interface TreeMenuItem {
  label: string
  danger?: boolean
  onClick: () => void
}

export function TreeContextMenu({
  x,
  y,
  items,
  onClose,
}: {
  x: number
  y: number
  items: TreeMenuItem[]
  onClose: () => void
}) {
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // 延后一拍绑定：创建菜单的同一事件（contextmenu）不能立刻把它关掉
    let bound = false
    const close = () => onClose()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      // 方向键 / Home / End 在菜单项间移动焦点（WAI-ARIA menu 约定）
      const items = menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')
      if (!items || items.length === 0) return
      const list = Array.from(items)
      const idx = list.indexOf(document.activeElement as HTMLButtonElement)
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Home' || e.key === 'End') {
        e.preventDefault()
        const next =
          e.key === 'Home'
            ? 0
            : e.key === 'End'
              ? list.length - 1
              : e.key === 'ArrowDown'
                ? (idx + 1) % list.length
                : (idx - 1 + list.length) % list.length
        list[next]?.focus()
      }
    }
    const t = setTimeout(() => {
      bound = true
      document.addEventListener('click', close)
      document.addEventListener('contextmenu', close)
    }, 0)
    document.addEventListener('keydown', onKey)
    // 键盘用户用 Shift+F10 / ContextMenu 键唤起时，焦点必须进入菜单才可操作
    menuRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus()
    return () => {
      clearTimeout(t)
      if (bound) {
        document.removeEventListener('click', close)
        document.removeEventListener('contextmenu', close)
      }
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  const left = Math.min(x, window.innerWidth - 180)
  const top = Math.min(y, window.innerHeight - 40 - items.length * 32)

  return createPortal(
    <div
      ref={menuRef}
      role="menu"
      className="fixed z-[120] min-w-[168px] rounded-[10px] border border-border bg-card py-1 shadow-[0_8px_28px_rgba(24,24,27,0.14)]"
      style={{ left, top }}
      onClick={(e) => e.stopPropagation()}
      onContextMenu={(e) => {
        e.preventDefault()
        e.stopPropagation()
      }}
    >
      {items.map((it) => (
        <button
          key={it.label}
          type="button"
          role="menuitem"
          className={
            'block w-full cursor-pointer px-3 py-[6px] text-left text-[12.5px] transition-colors hover:bg-secondary ' +
            (it.danger ? 'text-destructive' : 'text-secondary-foreground')
          }
          onClick={it.onClick}
        >
          {it.label}
        </button>
      ))}
    </div>,
    document.body,
  )
}

/** 行内删除确认条（不叠 modal；确认后移入 _已删除，可恢复） */
export function DeleteConfirm({
  name,
  onConfirm,
  onCancel,
}: {
  name: string
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="flex items-center gap-2 rounded-[7px] bg-destructive/5 px-2 py-1 text-[12px]">
      <span className="min-w-0 flex-1 truncate text-destructive" title={name}>
        移入「_已删除」？{name}
      </span>
      <button
        type="button"
        className="flex-none cursor-pointer font-[620] text-destructive"
        onClick={(e) => {
          e.stopPropagation()
          onConfirm()
        }}
      >
        确认
      </button>
      <button
        type="button"
        className="flex-none cursor-pointer text-muted-foreground"
        onClick={(e) => {
          e.stopPropagation()
          onCancel()
        }}
      >
        取消
      </button>
    </div>
  )
}
