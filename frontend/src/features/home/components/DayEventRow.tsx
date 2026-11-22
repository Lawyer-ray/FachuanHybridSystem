import { memo } from 'react'
import { Check } from 'lucide-react'

import type { CalendarEvent } from '../api'
import { cardTargetLine, cardTitle, cellMetaLines, isKeyKind } from '../api-meta'
import type { CalendarDensity } from '../calendar-density'
import { KIND_ROW } from '../constants'
import { cn } from '@/lib/utils'

/**
 * 事件级动作（打开详情 / 勾完成 / 右键菜单）。
 *
 * 收成一个对象而不是三个平铺 props：这组回调要从 HomePage 一路传到事件行
 * （CalendarPanel → DayCell → DayEventRow），逐项透传时每加一个事件级动作就要
 * 改 4 个文件的签名（加右键菜单那轮就是这么改的）；成对象后同样能让
 * `memo` 拿稳引用（HomePage 用 useMemo 固化）。
 */
export interface CalendarEventActions {
  /** 打开某条安排的详情（弹窗由调用方挂载——日历格、手机抽屉、今日卡共用同一个） */
  onOpenEvent: (e: CalendarEvent) => void
  /** 勾选完成 / 取消完成（合并事件的全部成员由调用方统一处理） */
  onToggleComplete: (e: CalendarEvent) => void
  /** 右键快捷菜单（光标坐标随事件带上）；不传则走浏览器默认菜单 */
  onEventContextMenu?: (e: CalendarEvent, pos: { x: number; y: number }) => void
}

interface Props {
  event: CalendarEvent
  /** wide=时间 + 标题 + 关联对象 + 律师 + 地点；medium=时间 + 标题 */
  density: Extract<CalendarDensity, 'wide' | 'medium'>
  actions: CalendarEventActions
}

/** 单条事件行：列表项级 memo（一个月最多 42 格 × 数行，父层任一视图态变化都会全量重渲） */
export const DayEventRow = memo(function DayEventRow({ event: e, density, actions }: Props) {
  const { onOpenEvent, onToggleComplete, onEventContextMenu } = actions
  const meta = cellMetaLines(e)
  const targetLine = cardTargetLine(e)

  return (
    <div
      data-calendar-event={e.id}
      role="button"
      tabIndex={0}
      className={cn(
        'flex flex-col justify-center gap-px rounded-[5px] px-[6px] py-[3px] text-[11.5px] transition-[filter] hover:brightness-95',
        KIND_ROW[e.kind],
        !isKeyKind(e.kind) && 'bg-secondary/70',
        e.is_completed && 'opacity-55',
      )}
      onClick={(ev) => {
        ev.stopPropagation()
        onOpenEvent(e)
      }}
      onKeyDown={(ev) => {
        // 键盘可达：Enter / Space 打开事件详情（等价点击事件行）
        if (ev.key !== 'Enter' && ev.key !== ' ') return
        // 行首完成勾选按钮自身可激活，按键交给按钮，不重复触发详情
        if ((ev.target as HTMLElement).closest('button')) return
        ev.preventDefault()
        // 不冒泡到日历格（否则会触发「点空白处新增」）
        ev.stopPropagation()
        onOpenEvent(e)
      }}
      onContextMenu={onEventContextMenu
        ? (ev) => {
            // 右键直达快捷菜单（删除等）：拦掉浏览器原生菜单，也不触发日历格的任何行为
            ev.preventDefault()
            ev.stopPropagation()
            onEventContextMenu(e, { x: ev.clientX, y: ev.clientY })
          }
        : undefined}
    >
      {/* 时间独占第一行，正文全部左对齐顶格开始。
          以前把时间做成固定 30px 的前导列，导致律师/地点两行要缩进
          到 30px 起，左侧白费一条——格子本来就窄，不能再浪费宽度。
          行首的完成勾选与时间同行，已完成时标题划线。 */}
      <span className="flex items-center gap-1">
        <button
          type="button"
          aria-label={e.is_completed ? '标记为未完成' : '标记为完成'}
          title={e.is_completed ? '标记为未完成' : '标记为完成'}
          onClick={(ev) => {
            // 勾选只切换完成态：不冒泡到事件行（详情）与日历格（新增）
            ev.stopPropagation()
            onToggleComplete(e)
          }}
          className={cn(
            'flex h-[12px] w-[12px] flex-none items-center justify-center rounded-full border-[1.5px] transition-colors',
            e.is_completed
              ? 'border-foreground bg-foreground text-background'
              : 'border-current/40 text-transparent hover:border-current',
          )}
        >
          <Check className="h-[8px] w-[8px]" strokeWidth={3} />
        </button>
        <span className="text-[10px] font-semibold tabular-nums opacity-80">{e.time}</span>
        {e.time_range && e.time_range !== e.time && (
          <span className="truncate text-[9px] tabular-nums opacity-55">-{e.time_range.split('-')[1]}</span>
        )}
      </span>
      {/* 主标题用 cardTitle（行动项优先）：后端 title 是「关联对象名优先」，
          绑了长合同名后格子里只剩合同名，看不出这条安排要做什么 */}
      <span className={cn('truncate font-medium leading-tight', e.is_completed && 'line-through')}>{cardTitle(e)}</span>
      {/* 中宽档只留「时间 + 标题」：多出的三行在 100px 不到的格子里每行剩一个字，
          反而看不出是哪件事；完整信息点开详情 / 手机开当日抽屉看 */}
      {density === 'wide' && targetLine && <span className="truncate text-[9.5px] opacity-70">{targetLine}</span>}
      {density === 'wide' && meta.primary && <span className="truncate text-[9.5px] opacity-75">{meta.primary}</span>}
      {density === 'wide' && meta.secondary && <span className="truncate text-[9.5px] opacity-60">{meta.secondary}</span>}
    </div>
  )
})
