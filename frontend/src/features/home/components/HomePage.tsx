import { useCallback, useMemo, useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { calendarKeys, fetchCalendarMonth } from '../api'
import { formatCN, formatWeekdayCN, parseKey, todayKey } from '../domain'
import { CalendarPanel, type CalendarView } from './CalendarPanel'
import { ToolDock } from './ToolDock'
import { AppNavbar } from '@/components/shared/AppNavbar'
import { PageFade } from '@/components/shared/PageFade'
import { InboxCard, QuickAdd, TodayCard } from './SideCards'
import { AddReminderDialog } from './AddReminderDialog'
import { DaySheet } from './DaySheet'
import type { InboxItem } from '../types'

/** 手机端展开抽屉的宽度阈值（与原型一致） */
const MOBILE_MAX = 760

function isMobile(): boolean {
  return typeof window !== 'undefined' && window.innerWidth < MOBILE_MAX
}

/** 点新增时的默认时刻：点今天取"现在"，点其他日期取 09:00 */
function defaultTimeFor(day: string, today: string): string {
  if (day !== today) return '09:00'
  const now = new Date()
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
}

/**
 * 首页 · 今日工作台。
 * 布局：左栏（大日历 + 快捷工具坞）、右栏（今日 + 待处理），窄屏单列。
 *
 * 日历视图月（view）在这里持有：CalendarPanel 只负责展示，切月由 view 变化
 * 驱动 useQuery 真正请求那个月——此前视图月困在 CalendarPanel 内部，翻月
 * 永远是空日历。今日相关数据（统计 / 今日卡 / 抽屉）固定用「今天所在月」
 * 的查询；view 与今天同月时两个 query 共享同一个 key，react-query 自动去重。
 */
export function HomePage() {
  const queryClient = useQueryClient()
  const today = useMemo(() => todayKey(), [])
  const [sheetDay, setSheetDay] = useState<string | null>(null)
  // 新增安排弹窗（day=null 关闭）；由日历空白格与手机抽屉「＋新增」共同打开
  const [adding, setAdding] = useState<{ day: string; time: string } | null>(null)

  const todayParts = useMemo(() => {
    const [y, m] = today.split('-').map(Number)
    return { year: y, month: m }
  }, [today])
  const [view, setView] = useState<CalendarView>(todayParts)

  /* 视图月日历（CalendarPanel 渲染 + 手机抽屉数据源）；今日月日历（统计 + 今日卡） */
  const viewQuery = useQuery({
    queryKey: calendarKeys.month(view.year, view.month),
    queryFn: () => fetchCalendarMonth(view.year, view.month),
    staleTime: 60_000,
    placeholderData: keepPreviousData, // 切月时保留上月格子，避免整版闪空
  })
  const todayQuery = useQuery({
    queryKey: calendarKeys.month(todayParts.year, todayParts.month),
    queryFn: () => fetchCalendarMonth(todayParts.year, todayParts.month),
    staleTime: 60_000,
  })

  const viewEventsByDay = useMemo(() => viewQuery.data?.days ?? {}, [viewQuery.data])
  const todayEventsByDay = useMemo(() => todayQuery.data?.days ?? {}, [todayQuery.data])
  const stats = useMemo(
    () => todayQuery.data?.stats ?? { today: 0, deadline_in_7days: 0, month_court: 0 },
    [todayQuery.data],
  )
  // 后端已按「时间升序 + 紧要排前」排好，直接取
  const todayEvents = useMemo(() => todayEventsByDay[today] ?? [], [todayEventsByDay, today])

  const invalidateCalendar = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: calendarKeys.all })
  }, [queryClient])

  const openAddDialog = useCallback(
    (day: string) => {
      setAdding({ day, time: defaultTimeFor(day, today) })
    },
    [today],
  )

  const notify = useCallback((msg: string) => toast.info(msg), [])

  /* 日历点某天：桌面端只高亮，手机端开抽屉 */
  const handleSelectDay = useCallback((key: string) => {
    if (isMobile()) setSheetDay(key)
  }, [])

  const handleOpenEvent = useCallback((e: import('../api').CalendarEvent) => {
    if (e.case_id) {
      toast.info(`打开案件 #${e.case_id}：${e.title}`)
      return
    }
    toast.info('这条安排还没关联案件，可到「案件台账」里查看')
  }, [])

  // 待处理里的材料包 → 跳到材料预处理详情。
  // 用 navigate 做 SPA 跳转，别用 window.location.assign（那是整页刷新，
  // 既丢状态也播不了过渡动画）。
  const navigate = useNavigate()
  const goPack = useCallback(
    (id: number) => {
      navigate(`/material-prep/${id}`)
    },
    [navigate],
  )

  const handleInboxOpen = useCallback(
    (item: InboxItem) => {
      if (item.kind === 'mat') {
        goPack(item.id)
        return
      }
      toast.info(`${item.title} —— 详情页正在开发中`)
    },
    [goPack],
  )

  const shiftMonth = useCallback((delta: number) => {
    setView((v) => {
      const m = v.month + delta
      if (m < 0) return { year: v.year - 1, month: 11 }
      if (m > 11) return { year: v.year + 1, month: 0 }
      return { year: v.year, month: m }
    })
  }, [])

  const goToday = useCallback(() => {
    setView(todayParts)
  }, [todayParts])

  return (
    <div className="min-h-screen bg-background">
      <AppNavbar onNotify={notify} />

      {/* 内容区包一层入场过渡：navbar 不变，只有下面这部分播动画 */}
      <PageFade>
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
            <QuickAdd onAdded={invalidateCalendar} />
          </div>

          <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
            {/* 左：日历 + 工具 */}
            <div className="min-w-0">
              <CalendarPanel
                today={today}
                view={view}
                onShiftMonth={shiftMonth}
                onGoToday={goToday}
                eventsByDay={viewEventsByDay}
                stats={stats}
                loading={viewQuery.isLoading}
                onSelectDay={handleSelectDay}
                onOpenEvent={handleOpenEvent}
                onOpenAdd={openAddDialog}
              />
              <ToolDock />
            </div>

            {/* 右：今日 + 待处理 */}
            <div className="flex min-w-0 flex-col gap-5">
              <TodayCard events={todayEvents} loading={todayQuery.isLoading} onOpenEvent={handleOpenEvent} />
              <InboxCard onOpen={handleInboxOpen} />
            </div>
          </div>
        </main>
      </PageFade>

      {/* 手机端当日安排抽屉 */}
      <DaySheet
        day={sheetDay}
        today={today}
        events={sheetDay ? (viewEventsByDay[sheetDay] ?? []) : []}
        onClose={() => setSheetDay(null)}
        onOpenEvent={handleOpenEvent}
        onAdd={() => sheetDay && openAddDialog(sheetDay)}
      />

      {/* 新增安排弹窗：日历空白格 / 手机抽屉「＋新增」共用 */}
      <AddReminderDialog
        day={adding?.day ?? null}
        defaultTime={adding?.time ?? '09:00'}
        onClose={() => setAdding(null)}
        onSaved={invalidateCalendar}
      />
    </div>
  )
}
