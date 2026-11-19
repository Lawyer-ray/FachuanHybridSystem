import { useEffect, useState } from 'react'
import { Check, ChevronLeft, ChevronRight } from 'lucide-react'

import { WEEKDAYS } from '../constants'
import type { CalendarEvent, CalendarStats } from '../api'
import { densityForWidth, maxRowsForWidth } from '../calendar-density'
import { buildMonthGrid } from '../domain'
import { BTN, BTN_ICON, PANEL } from '../ui'
import { useElementWidth } from '@/hooks/use-element-width'
import { useMediaQuery } from '@/hooks/use-media'
import { cn } from '@/lib/utils'
import { DayCell } from './DayCell'

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
  /** 选中某天（桌面端高亮 / 移动端开当日抽屉由调用方决定） */
  onSelectDay: (key: string) => void
  /** 打开某条安排的详情（弹窗由调用方挂载——日历格、手机抽屉、今日卡共用同一个） */
  onOpenEvent: (e: CalendarEvent) => void
  /** 勾选完成 / 取消完成（合并事件的全部成员由调用方统一处理） */
  onToggleComplete: (e: CalendarEvent) => void
  /** 点日历格空白处 → 新增该日安排（弹窗由调用方挂载）。仅桌面端：手机端点格子一律开当日抽屉，新增走抽屉里的「＋新增」 */
  onOpenAdd: (key: string) => void
  /** 右键事件行 → 快捷菜单（光标坐标随事件带上）；可选，不传则右键走浏览器默认行为 */
  onEventContextMenu?: (e: CalendarEvent, pos: { x: number; y: number }) => void
  /** 密度是否降到紧凑档（点格子=看这一天）。调用方据此决定开当日抽屉还是弹新增 */
  onCompactChange?: (compact: boolean) => void
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
  onToggleComplete,
  onOpenAdd,
  onEventContextMenu,
  onCompactChange,
}: Props) {
  const [selected, setSelected] = useState(today)
  // 跨零点跟随：useState(today) 只取初值，长开页面跨天后默认高亮会冻结在昨天。
  // today 是 HomePage useToday 的 dateKey（跨天才换引用），这里仅当用户没有
  // 选中别的日子（仍停在旧今天或更早）时跟着挪到新今天，不覆盖用户选择。
  useEffect(() => {
    setSelected((prev) => (prev <= today ? today : prev))
  }, [today])
  // 内容密度（每格几行、放不给放副标题）与每格最多行数，全部按**面板实测净宽**
  // 判定，不看视口：AI 助手并排让位后面板净宽比视口窄数百像素，视口量不到它——
  // 以前只在「最多几行」上按净宽、内容形态仍按视口，于是并排 / 分屏时日历在
  // ~90px 宽的格子里硬塞五行卡片（每行只剩一两个字）。阈值见 calendar-density.ts。
  const [sectionRef, sectionWidth] = useElementWidth<HTMLElement>()
  // 手机视口一律紧凑档：手机上面板必然窄，且「点格子开当日抽屉」是手机唯一的
  // 详情入口（格子只有 ~50px 宽，事件行放不下也点不准）。宽视口下再按净宽分三档。
  const isPhone = useMediaQuery('(max-width: 760px)')
  const density = isPhone ? 'compact' : densityForWidth(sectionWidth, 'wide')
  const maxRows = maxRowsForWidth(sectionWidth)
  const compact = density === 'compact'
  useEffect(() => {
    onCompactChange?.(compact)
  }, [compact, onCompactChange])

  const cells = buildMonthGrid(view.year, view.month)

  const pickDay = (key: string) => {
    setSelected(key)
    onSelectDay(key)
  }

  return (
    <section ref={sectionRef} className={`${PANEL} @container`}>
      {/* 头部：月份导航 + 统计。窄面板（助手并排 / 分屏 / 手机）下统计整行下沉并
          两端对齐，不再挤在月份右侧换来换去地折行 */}
      <div className="flex flex-wrap items-center gap-2 px-4 pb-3 pt-4 @max-[560px]:gap-x-1.5 @max-[560px]:px-3 @max-[560px]:pt-3">
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

        {/* flex-wrap：三项统计各带 whitespace-nowrap，极窄时宁可折成两行也不横向溢出 */}
        <div className="ml-auto flex flex-wrap gap-x-4 gap-y-[2px] text-[11.5px] whitespace-nowrap text-muted-foreground @max-[560px]:ml-0 @max-[560px]:w-full @max-[560px]:justify-between @max-[560px]:gap-x-2 @max-[560px]:text-[11px]">
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
          <DayCell
            key={cell.key ?? `blank-${cell.day}`}
            cell={cell}
            today={today}
            selected={cell.key === selected}
            events={cell.key ? (eventsByDay[cell.key] ?? []) : []}
            maxRows={maxRows}
            density={density}
            onPick={pickDay}
            onOpenDetail={onOpenEvent}
            onOpenAdd={onOpenAdd}
            onToggleComplete={onToggleComplete}
            onEventContextMenu={onEventContextMenu}
          />
        ))}
        {loading && (
          <div className="absolute inset-0 grid place-items-center rounded-b-[14px] bg-card/60 text-[12px] text-muted-foreground">
            正在载入日程…
          </div>
        )}
      </div>

      {/* 图例（窄面板允许折行，不横向溢出） */}
      <div className="flex flex-wrap gap-x-[18px] gap-y-[3px] px-4 pb-[13px] text-[10.5px] text-muted-foreground @max-[560px]:px-3">
        <span className="flex items-center gap-1.5">
          <i className="h-[7px] w-[7px] flex-none rounded-full bg-status-red" />
          紧要 · 庭期 / 期限
        </span>
        <span className="flex items-center gap-1.5">
          <i className="h-[7px] w-[7px] flex-none rounded-full bg-input" />
          常规 · 日程 / 跟进
        </span>
        <span className="flex items-center gap-1.5">
          <i className="flex h-[11px] w-[11px] flex-none items-center justify-center rounded-full border-[1.5px] border-foreground bg-foreground text-background">
            <Check className="h-[7px] w-[7px]" strokeWidth={3} />
          </i>
          已完成
        </span>
      </div>
    </section>
  )
}
