import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Check, Trash2 } from 'lucide-react'

import type { CalendarEvent } from '../api'

/** 菜单预估尺寸：视口边缘翻转用，不必精确 */
const MENU_W = 172
const MENU_H = 84

interface ContextTarget {
  event: CalendarEvent
  /** contextmenu 事件的 clientX / clientY（视口坐标，菜单 fixed 定位用） */
  x: number
  y: number
}

interface Props {
  /** null = 关闭 */
  target: ContextTarget | null
  onClose: () => void
  /** 标记完成 / 恢复（合并事件的全部成员由调用方统一处理） */
  onToggleComplete: (e: CalendarEvent) => void
  /** 删除（合并事件的全部成员由调用方统一处理）；仅 event.can_delete 时展示 */
  onDelete: (e: CalendarEvent) => void
}

/**
 * 日历事件的右键快捷菜单：光标处弹出「标记完成 / 删除」，删除不再需要
 * 先开详情弹窗。挂在 HomePage（与本页其他弹窗同架构，本组件不自持数据）。
 *
 * 快捷删除是**直接下发**的，不再二次确认——用户要的就是右键即删；
 * 误删的兜底是失败回滚 + 后端「谁创建谁删」权限闸（菜单项本身也按
 * can_delete 显隐）。
 */
export function EventContextMenu({ target, onClose, onToggleComplete, onDelete }: Props) {
  const menuRef = useRef<HTMLDivElement>(null)
  // 视口边缘翻转后的实际落点
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)

  const event = target?.event
  const x = target?.x ?? 0
  const y = target?.y ?? 0

  // 用真实菜单尺寸做翻转（useLayoutEffect 避免先闪一帧错位）
  useLayoutEffect(() => {
    if (!target) {
      setPos(null)
      return
    }
    const rect = menuRef.current?.getBoundingClientRect()
    const w = rect?.width ?? MENU_W
    const h = rect?.height ?? MENU_H
    setPos({
      left: x + w > window.innerWidth ? Math.max(4, x - w) : x,
      top: y + h > window.innerHeight ? Math.max(4, y - h) : y,
    })
  }, [target, x, y])

  // ESC / 滚动 / 改窗口尺寸即关闭（scroll 用捕获：日历格内滚动也要算）
  useEffect(() => {
    if (!target) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('scroll', onClose, true)
    window.addEventListener('resize', onClose)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('scroll', onClose, true)
      window.removeEventListener('resize', onClose)
    }
  }, [target, onClose])

  if (!target || !event) return null

  return (
    <>
      {/* 透明遮罩：点别处 / 右键别处都收起菜单。z 基线：本页弹窗 z-[130]、抽屉 z-61，
          菜单夹在中间 */}
      <div
        className="fixed inset-0 z-[119]"
        onClick={onClose}
        onContextMenu={(e) => {
          e.preventDefault()
          onClose()
        }}
        aria-hidden
      />
      <div
        ref={menuRef}
        role="menu"
        aria-label={`「${event.title}」快捷操作`}
        style={{ left: pos?.left ?? x, top: pos?.top ?? y, visibility: pos ? 'visible' : 'hidden' }}
        className="fixed z-[120] min-w-[160px] overflow-hidden rounded-[10px] border border-border bg-card py-1 shadow-[0_10px_28px_rgba(0,0,0,.14)]"
      >
        <button
          type="button"
          role="menuitem"
          onClick={() => {
            onToggleComplete(event)
            onClose()
          }}
          className="flex w-full items-center gap-2 px-3 py-[7px] text-left text-[12px] text-foreground transition-colors hover:bg-secondary"
        >
          <Check className="h-3.5 w-3.5" />
          {event.is_completed ? '恢复为未完成' : '标记完成'}
        </button>
        {event.can_delete && (
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onDelete(event)
              onClose()
            }}
            className="flex w-full items-center gap-2 px-3 py-[7px] text-left text-[12px] text-destructive transition-colors hover:bg-destructive/10"
          >
            <Trash2 className="h-3.5 w-3.5" />
            删除
            {event.members > 1 && <span className="ml-auto text-[10px] opacity-70">共 {event.members} 条</span>}
          </button>
        )}
      </div>
    </>
  )
}
