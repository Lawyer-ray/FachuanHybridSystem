import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { KIND_ROW, WEEKDAYS } from '../constants'
import { isKeyKind } from '../api-meta'
import type { CalendarEvent, CalendarStats } from '../api'
import { buildMonthGrid, formatCN, parseKey } from '../domain'
import { briefLine, cellMetaLines } from '../api-meta'
import { EventDetailDialog } from './EventDetailDialog'
import { BTN, BTN_ICON, PANEL } from '../ui'
import { cn } from '@/lib/utils'

/** 每天最多显示几行事件（超出折叠成「+N 更多」），按窗口宽度自适应 */
function maxRowsPerDay(): number {
  const w = window.innerWidth
  return w >= 2400 ? 5 : w >= 1600 ? 4 : 3
}

export interface CalendarView {
  year: number
  /** 0-based 月（JS Date 口径：0 = 一月）；头部显示与查询边界各自 +1 */
  month: number
}

interface Props {
  today: string
  /** 当前视图月（受控：由 HomePage 持有并驱动取数，切月才会真正请求那一个月） */
  view: CalendarView
  onShiftMonth: (delta: number) => void
  onGoToday: () => void
  eventsByDay: Record<string, CalendarEvent[]>
  stats: CalendarStats
  loading: boolean
  /** 选中某天（桌面端高亮 / 移动端开抽屉由调用方决定） */
  onSelectDay: (key: string) => void
  /** 打开某条安排（跳案件/详情；未实现的给提示） */
  onOpenEvent: (e: CalendarEvent) => void
  /** 点日历格空白处 → 新增该日安排（弹窗由调用方挂载） */
  onOpenAdd: (key: string) => void
}

/** 大日历面板：月份切换 + 周一起点月历 + 事件行 + 悬停摘要 + 统计。
 *  纯展示受控组件：视图月与数据都在 HomePage，本组件不own取数、不own弹窗。 */
export function CalendarPanel({
  today,
  view,
  onShiftMonth,
  onGoToday,
  eventsByDay,
  stats,
  loading,
  onSelectDay,
  onOpenEvent,
  onOpenAdd,
}: Props) {
  const [selected, setSelected] = useState(today)
  const [maxRows, setMaxRows] = useState(maxRowsPerDay)
  // 详情弹窗：点日历格里的事件打开
  const [detail, setDetail] = useState<CalendarEvent | null>(null)

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

  const cells = buildMonthGrid(view.year, view.month)

  const pickDay = (key: string) => {
    setSelected(key)
    onSelectDay(key)
  }

  return (
    <section className={PANEL}>
      {/* 头部：月份导航 + 统计 */}
      <div className="flex flex-wrap items-center gap-2 px-4 pb-3 pt-4">
        <button type="button" className={BTN_ICON} onClick={() => onShiftMonth(-1)} title="上个月" aria-label="上个月">
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
        <button type="button" className={BTN_ICON} onClick={() => onShiftMonth(1)} title="下个月" aria-label="下个月">
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
        <div className="text-[16px] font-semibold tracking-[-0.01em]">
          {view.month + 1} 月<span className="ml-[7px] text-[12px] font-normal text-muted-foreground">{view.year}</span>
        </div>
        <button type="button" className={BTN} onClick={onGoToday} title="回到今天">
          今天
        </button>

        <div className="ml-auto flex gap-4 text-[11.5px] whitespace-nowrap text-muted-foreground">
          <span className="flex items-baseline gap-1">
            今日 <b className="tabular-nums font-semibold text-status-red">{stats.today}</b> 件
          </span>
          <span>
            7 日内 <b className="tabular-nums font-semibold text-foreground">{stats.deadline_in_7days}</b> 件到期
          </span>
          <span>
            本月 <b className="tabular-nums font-semibold text-foreground">{stats.month_court}</b> 个庭
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

      {/* 日期网格：行数按需自适应，避免切月时高度抖动 */}
      <div className="relative grid grid-cols-7 px-2.5 py-1 [&>div:nth-last-child(-n+7)]:border-b-0">
        {cells.map((cell) => (
          <DayCellView
            key={cell.key ?? `blank-${cell.day}`}
            cell={cell}
            today={today}
            selected={cell.key === selected}
            events={cell.key ? (eventsByDay[cell.key] ?? []) : []}
            maxRows={maxRows}
            onPick={pickDay}
            onOpenDetail={setDetail}
            onOpenAdd={onOpenAdd}
          />
        ))}
        {loading && (
          <div className="absolute inset-0 grid place-items-center rounded-b-[14px] bg-card/60 text-[12px] text-muted-foreground">
            正在载入日程…
          </div>
        )}
      </div>

      {/* 事件详情弹窗 */}
      <EventDetailDialog event={detail} onClose={() => setDetail(null)} onOpenCase={onOpenEvent} />

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
  events: CalendarEvent[]
  maxRows: number
  onPick: (key: string) => void
  onOpenDetail: (e: CalendarEvent) => void
  /** 点本格空白处 → 新增该日安排 */
  onOpenAdd: (key: string) => void
}

function DayCellView({ cell, today, selected, events, maxRows, onPick, onOpenAdd, onOpenDetail }: CellProps) {
  if (!cell.key || cell.day == null) return <div className="min-h-[clamp(132px,12vw,208px)] border-r border-b border-border-light" />

  const isToday = cell.key === today
  const shown = events.slice(0, maxRows)
  const hidden = events.length - shown.length

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${cell.day} 日${events.length ? `，${events.length} 个安排` : ''}，回车新增该日安排`}
      className={cn(
        'group relative min-h-[clamp(132px,12vw,208px)] cursor-pointer border-r border-b border-border-light p-[7px] transition-colors last:border-r-0 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset',
        !cell.inMonth && 'opacity-30',
        selected && 'bg-secondary/60',
        isToday && 'bg-status-red-bg/40',
      )}
      onClick={(ev) => {
        // 点在事件行 / 「+N 更多」上不算"点空白处"，只选中该日（新增弹窗由 onOpenAdd 负责）
        const target = ev.target as HTMLElement
        if (target.closest('[data-calendar-event], [data-calendar-more]')) {
          onPick(cell.key as string)
          return
        }
        onOpenAdd(cell.key as string)
      }}
      onKeyDown={(ev) => {
        // 键盘可达：Enter / Space 等价于点空白处（打开该日新增）；事件行详情仍走鼠标
        if (ev.key === 'Enter' || ev.key === ' ') {
          ev.preventDefault()
          onPick(cell.key as string)
          onOpenAdd(cell.key as string)
        }
      }}
      title="点空白处新增该日安排"
    >
      <div className="mb-[5px] flex items-center justify-center gap-[3px]">
        <span
          className={cn(
            'flex h-[22px] w-[22px] items-center justify-center rounded-full text-[12px] leading-none font-medium tabular-nums',
            isToday && 'bg-status-red font-bold text-white',
          )}
        >
          {cell.day}
        </span>
        {/* 当日条数角标：与 admin 日历的 reminder-day-count 一致 */}
        {events.length > 0 && (
          <span className="rounded-full border border-border bg-secondary px-[5px] py-[1px] text-[9px] font-semibold tabular-nums text-muted-foreground">
            {events.length}
          </span>
        )}
      </div>

      <div className={cn('flex flex-col gap-[2px]', 'max-[760px]:hidden')}>
        {shown.map((e) => {
          const meta = cellMetaLines(e)
          return (
            <div
              key={e.id}
              data-calendar-event={e.id}
              className={cn(
                'flex flex-col justify-center gap-px rounded-[5px] px-[6px] py-[3px] text-[11.5px] transition-[filter] hover:brightness-95',
                KIND_ROW[e.kind],
                !isKeyKind(e.kind) && 'bg-secondary/70',
              )}
              onClick={(ev) => {
                ev.stopPropagation()
                onOpenDetail(e)
              }}
            >
              {/* 时间独占第一行，正文全部左对齐顶格开始。
                  以前把时间做成固定 30px 的前导列，导致律师/地点两行要缩进
                  到 30px 起，左侧白费一条——格子本来就窄，不能再浪费宽度。 */}
              <span className="flex items-baseline gap-1">
                <span className="text-[10px] font-semibold tabular-nums opacity-80">{e.time}</span>
                {e.time_range && e.time_range !== e.time && (
                  <span className="truncate text-[9px] tabular-nums opacity-55">-{e.time_range.split('-')[1]}</span>
                )}
              </span>
              <span className="truncate font-medium leading-tight">{e.title}</span>
              {meta.primary && <span className="truncate text-[9.5px] opacity-75">{meta.primary}</span>}
              {meta.secondary && <span className="truncate text-[9.5px] opacity-60">{meta.secondary}</span>}
            </div>
          )
        })}
        {hidden > 0 && (
          <span
            data-calendar-more
            className="mt-[1px] self-start rounded-[6px] border border-input bg-secondary px-2 py-[2px] text-[10.5px] font-semibold text-secondary-foreground"
          >
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
            {/* parseKey 而非 new Date(key)：后者按 UTC 零点解析，西半球时区会退一天 */}
            {(isToday ? '今天 · ' : '') + formatCN(parseKey(cell.key))}
          </div>
          {events.map((e) => (
            <div key={e.id} className="flex items-baseline gap-[7px]">
              <span className="w-8 flex-none text-[10px] text-background/60 tabular-nums">{e.time}</span>
              <span className="truncate font-medium">{e.title}</span>
              <span className="max-w-[110px] truncate text-[10.5px] text-background/50">{briefLine(e)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
