import { useCallback, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { fetchCalendarMonth } from '../api'
import { formatCN, formatWeekdayCN, parseKey, todayKey } from '../domain'
import { CalendarPanel } from './CalendarPanel'
import { ToolDock } from './ToolDock'
import { AppNavbar } from '@/components/shared/AppNavbar'
import { InboxCard, QuickAdd, TodayCard } from './SideCards'
import { DaySheet } from './DaySheet'
import type { CalendarEvent } from '../api'
import type { InboxItem } from '../types'

/** 手机端展开抽屉的宽度阈值（与原型一致） */
const MOBILE_MAX = 760

function isMobile(): boolean {
  return typeof window !== 'undefined' && window.innerWidth < MOBILE_MAX
}

/**
 * 首页 · 今日工作台。
 * 布局：左栏（大日历 + 快捷工具坞）、右栏（今日 + 待处理），窄屏单列。
 */
export function HomePage() {
  const queryClient = useQueryClient()
  const today = useMemo(() => todayKey(), [])
  const [sheetDay, setSheetDay] = useState<string | null>(null)

  const todayParts = useMemo(() => {
    const [y, m] = today.split('-').map(Number)
    return { year: y, month: m }
  }, [today])

  /* 日历视图：合并 / 统计都由后端算好，前端只负责渲染 */
  const calendarQuery = useQuery({
    queryKey: ['home-calendar', todayParts.year, todayParts.month],
    queryFn: () => fetchCalendarMonth(todayParts.year, todayParts.month),
    staleTime: 60_000,
  })

  const calendar = calendarQuery.data
  const eventsByDay = useMemo(() => calendar?.days ?? {}, [calendar])
  const stats = useMemo(
    () => calendar?.stats ?? { today: 0, deadline_in_7days: 0, month_court: 0 },
    [calendar],
  )
  // 后端已按「时间升序 + 紧要排前」排好，直接取
  const todayEvents = useMemo(() => eventsByDay[today] ?? [], [eventsByDay, today])

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['home-calendar'] })
  }, [queryClient])

  const notify = useCallback((msg: string) => toast.info(msg), [])

  /* 日历点某天：桌面端只高亮，手机端开抽屉 */
  const handleSelectDay = useCallback((key: string) => {
    if (isMobile()) setSheetDay(key)
  }, [])

  const handleOpenEvent = useCallback((e: CalendarEvent) => {
    if (e.case_id) {
      toast.info(`打开案件 #${e.case_id}：${e.title}`)
      return
    }
    toast.info('这条安排还没关联案件，可到「案件台账」里查看')
  }, [])

  const handleInboxOpen = useCallback((item: InboxItem) => {
    if (item.kind === 'mat') {
      window.location.assign(`/material-prep/${item.id}`)
      return
    }
    toast.info(`${item.title} —— 详情页正在开发中`)
  }, [])

  const handleInboxAction = useCallback((item: InboxItem) => {
    if (item.kind === 'mat') {
      window.location.assign(`/material-prep/${item.id}`)
      return
    }
    toast.info(`「${item.title}」→ ${item.action}：收件箱操作正在开发中`)
  }, [])

  const handleAdd = useCallback(() => {
    toast.info('新增安排：请用「快速记一笔」，写具体日期即可（如 2026-09-28 09:30 开庭 …）')
  }, [])

  return (
    <div className="min-h-screen bg-background">
      <AppNavbar onNotify={notify} />

      <main className="mx-auto max-w-[1920px] px-[32px] pt-[26px] pb-20 max-[760px]:px-[14px] max-[760px]:pt-[18px]">
        {/* 问候 + 快速记一笔 */}
        <div className="mb-5 flex flex-wrap items-end gap-[18px]">
          <div className="min-w-0">
            <h1 className="text-[26px] leading-[1.2] font-bold tracking-[-0.025em] max-[760px]:text-[21px]">
              {formatCN(parseKey(today))}{' '}
              <span className="text-[19px] font-normal text-secondary-foreground max-[760px]:text-[17px]">
                {formatWeekdayCN(parseKey(today))}
              </span>
            </h1>
            <div className="mt-[3px] text-[12.5px] text-secondary-foreground">
              今天 <b className="font-semibold text-status-red">{stats.today}</b> 件事 ·{' '}
              <b className="font-semibold text-status-red">{stats.deadline_in_7days}</b> 件紧要事项 7 日内到期 · 本月还有{' '}
              <b className="font-semibold">{stats.month_court}</b> 个庭期
            </div>
          </div>
          <QuickAdd onAdded={refresh} />
        </div>

        <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
          {/* 左：日历 + 工具 */}
          <div className="min-w-0">
            <CalendarPanel
              today={today}
              eventsByDay={eventsByDay}
              stats={stats}
              loading={calendarQuery.isLoading}
              onSelectDay={handleSelectDay}
              onOpenEvent={handleOpenEvent}
              onAdd={handleAdd}
            />
            <ToolDock />
          </div>

          {/* 右：今日 + 待处理 */}
          <div className="flex min-w-0 flex-col gap-5">
            <TodayCard events={todayEvents} loading={calendarQuery.isLoading} onOpenEvent={handleOpenEvent} />
            <InboxCard onOpen={handleInboxOpen} onAction={handleInboxAction} />
          </div>
        </div>
      </main>

      {/* 手机端当日安排抽屉 */}
      <DaySheet
        day={sheetDay}
        today={today}
        events={sheetDay ? (eventsByDay[sheetDay] ?? []) : []}
        onClose={() => setSheetDay(null)}
        onOpenEvent={handleOpenEvent}
        onAdd={handleAdd}
      />
    </div>
  )
}
