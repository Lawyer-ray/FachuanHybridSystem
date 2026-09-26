import { useEffect, useMemo, useState } from 'react'
import { CalendarPlus, ChevronLeft, ChevronRight } from 'lucide-react'

import { KIND_ROW, WEEKDAYS, isKeyKind } from '../constants'
import type { DayEvent } from '../types'
import { buildMonthGrid, formatCN, parseKey } from '../domain'
import type { DeskStats } from '../domain'
import { BTN, BTN_ICON, PANEL } from '../ui'
import { cn } from '@/lib/utils'

interface Props {
  today: string
  eventsByDay: Map<string, DayEvent[]>
  stats: DeskStats
  loading: boolean
  /** 选中某天（桌面端高亮 / 移动端开抽屉由调用方决定） */
  onSelectDay: (key: string) => void
  /** 打开某条安排（跳案件/详情；未实现的给提示） */
  onOpenEvent: (e: DayEvent) => void
  /** 新增安排 */
  onAdd: () => void
}

/** 每天最多显示几行事件（超出折叠成「+N 更多」），按窗口宽度自适应 */
function maxRowsPerDay(): number {
  const w = window.innerWidth
  return w >= 2400 ? 6 : w >= 1600 ? 5 : w >= 1100 ? 4 : 3
}

/** 大日历面板：月份切换 + 周一起点月历 + 事件行 + 悬停摘要 + 统计 */
export function CalendarPanel({ today, eventsByDay, stats, loading, onSelectDay, onOpenEvent, onAdd }: Props) {
  const todayDate = parseKey(today)
  const [view, setView] = useState({ year: todayDate.getFullYear(), month: todayDate.getMonth() })
  const [selected, setSelected] = useState(today)
  const [maxRows, setMaxRows] = useState(maxRowsPerDay)

  // 窗口尺寸变化时重新计算每格行数（与原型一致，带防抖）
  useEffect(() => {
    let timer = 0
    const onResize = () => {
      window.clearTimeout(timer)
      timer = window.setTimeout(() => setMaxRows(maxRowsPerDay()), 120)
    }
    window.addEventListener('resize', onResize)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('resize', onResize)
    }
  }, [])

  const cells = useMemo(() => buildMonthGrid(view.year, view.month), [view])

  const shiftMonth = (delta: number) => {
    setView((v) => {
      const m = v.month + delta
      if (m < 0) return { year: v.year - 1, month: 11 }
      if (m > 11) return { year: v.year + 1, month: 0 }
      return { year: v.year, month: m }
    })
  }

  const goToday = () => {
    setView({ year: todayDate.getFullYear(), month: todayDate.getMonth() })
    setSelected(today)
  }

  const pickDay = (key: string) => {
    setSelected(key)
    onSelectDay(key)
  }

  return (
    <section className={PANEL}>
      {/* 头部：月份导航 + 统计 */}
      <div className="flex flex-wrap items-center gap-2 px-4 pb-3 pt-4">
        <button type="button" className={BTN_ICON} onClick={() => shiftMonth(-1)} title="上个月" aria-label="上个月">
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
        <button type="button" className={BTN_ICON} onClick={() => shiftMonth(1)} title="下个月" aria-label="下个月">
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
        <div className="text-[16px] font-semibold tracking-[-0.01em]">
          {view.month + 1} 月<span className="ml-[7px] text-[12px] font-normal text-muted-foreground">{view.year}</span>
        </div>
        <button type="button" className={BTN} onClick={goToday}>
          今天
        </button>
        <button type="button" className={BTN + ' ml-2'} onClick={onAdd}>
          <CalendarPlus className="h-3.5 w-3.5" />
          新增安排
        </button>

        <div className="ml-auto flex gap-4 text-[11.5px] whitespace-nowrap text-muted-foreground">
          <span className="flex items-baseline gap-1">
            今日 <b className="tabular-nums font-semibold text-status-red">{stats.todayCount}</b> 件
          </span>
          <span>
            7 日内 <b className="tabular-nums font-semibold text-foreground">{stats.deadlineIn7}</b> 件到期
          </span>
          <span>
            本月 <b className="tabular-nums font-semibold text-foreground">{stats.courtThisMonth}</b> 个庭
          </span>
        </div>
      </div>

      {/* 星期标题（周一起点） */}
      <div className="grid grid-cols-7 border-b border-border px-2.5">
        {WEEKDAYS.map((w, i) => (
          <span key={w} className={cn('py-[7px] text-center text-[10.5px] text-muted-foreground', i >= 5 && 'text-muted-foreground/60')}>
            {w}
          </span>
        ))}
      </div>

      {/* 日期网格：6 行 42 格，避免切月时高度抖动 */}
      <div className="relative grid grid-cols-7 px-2.5 py-1">
        {cells.map((cell) => (
          <DayCellView
            key={cell.key ?? `blank-${cell.day}`}
            cell={cell}
            today={today}
            selected={cell.key === selected}
            events={cell.key ? (eventsByDay.get(cell.key) ?? []) : []}
            maxRows={maxRows}
            onPick={pickDay}
            onOpenEvent={onOpenEvent}
          />
        ))}
        {loading && (
          <div className="absolute inset-0 grid place-items-center rounded-b-[14px] bg-card/60 text-[12px] text-muted-foreground">
            正在载入日程…
          </div>
        )}
      </div>

      {/* 图例 */}
      <div className="flex gap-[18px] px-4 pb-[13px] text-[10.5px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <i className="h-[7px] w-[7px] flex-none rounded-full bg-status-red" />
          紧要 · 庭期 / 期限
        </span>
        <span className="flex items-center gap-1.5">
          <i className="h-[7px] w-[7px] flex-none rounded-full bg-input" />
          常规 · 日程 / 跟进
        </span>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ 单日格 */

interface CellProps {
  cell: { key: string | null; day: number | null; inMonth: boolean }
  today: string
  selected: boolean
  events: DayEvent[]
  maxRows: number
  onPick: (key: string) => void
  onOpenEvent: (e: DayEvent) => void
}

function DayCellView({ cell, today, selected, events, maxRows, onPick, onOpenEvent }: CellProps) {
  if (!cell.key || cell.day == null) return <div className="min-h-[clamp(116px,9.2vw,172px)] border-r border-b border-border-light" />

  const isToday = cell.key === today
  const shown = events.slice(0, maxRows)
  const hidden = events.length - shown.length

  return (
    <div
      className={cn(
        'group relative min-h-[clamp(116px,9.2vw,172px)] cursor-pointer border-r border-b border-border-light p-[7px] transition-colors last:border-r-0',
        !cell.inMonth && 'opacity-30',
        selected && 'bg-secondary/60',
        isToday && 'bg-status-red-bg/40',
      )}
      onClick={() => onPick(cell.key as string)}
    >
      <div className="mb-[5px] flex items-center justify-center">
        <span
          className={cn(
            'flex h-[22px] w-[22px] items-center justify-center rounded-full text-[12px] leading-none font-medium tabular-nums',
            isToday && 'bg-status-red font-bold text-white',
          )}
        >
          {cell.day}
        </span>
      </div>

      <div className={cn('flex flex-col gap-[2px]', 'max-[760px]:hidden')}>
        {shown.map((e) => (
          <div
            key={e.id}
            className={cn(
              'flex min-h-[20px] items-center gap-1.5 rounded-[5px] px-1.5 py-[2px] text-[11.5px] transition-[filter] hover:brightness-95',
              KIND_ROW[e.kind],
              !isKeyKind(e.kind) && 'bg-secondary/70',
            )}
            onClick={(ev) => {
              ev.stopPropagation()
              onOpenEvent(e)
            }}
          >
            <span className="w-[30px] flex-none text-[10px] font-semibold tabular-nums opacity-80">{e.time}</span>
            <span className="truncate font-medium">{e.title}</span>
          </div>
        ))}
        {hidden > 0 && (
          <span className="mt-[1px] self-start rounded-[6px] border border-input bg-secondary px-2 py-[2px] text-[10.5px] font-semibold text-secondary-foreground">
            + {hidden} 更多
          </span>
        )}
      </div>

      {/* 手机端：只显示圆点 */}
      {events.length > 0 && (
        <div className="mt-[2px] hidden items-center justify-center gap-[3px] max-[760px]:flex">
          {events.slice(0, 4).map((e) => (
            <i key={e.id} className={cn('h-[6px] w-[6px] flex-none rounded-full', isKeyKind(e.kind) ? 'bg-status-red' : 'bg-input')} />
          ))}
          {events.length > 4 && <em className="text-[9px] leading-none text-muted-foreground">+{events.length - 4}</em>}
        </div>
      )}

      {/* 悬停摘要 */}
      {events.length > 0 && (
        <div className="pointer-events-none absolute bottom-[calc(100%+4px)] left-1/2 z-40 hidden w-[300px] max-w-[330px] -translate-x-1/2 scale-95 rounded-[11px] bg-foreground p-[11px_14px] text-[11.5px] leading-[1.5] text-background opacity-0 shadow-[0_8px_24px_rgba(0,0,0,.16)] transition-[opacity,transform,visibility] group-hover:visible group-hover:scale-100 group-hover:opacity-100 min-[761px]:block">
          <div className="mb-1.5 text-[10px] text-background/60">
            {(isToday ? '今天 · ' : '') + formatCN(new Date(cell.key))}
          </div>
          {events.map((e) => (
            <div key={e.id} className="flex items-baseline gap-[7px]">
              <span className="w-8 flex-none text-[10px] text-background/60 tabular-nums">{e.time}</span>
              <span className="truncate font-medium">{e.title}</span>
              <span className="max-w-[110px] truncate text-[10.5px] text-background/50">{e.subtitle}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
