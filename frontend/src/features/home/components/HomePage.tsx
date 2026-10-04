import { useCallback, useMemo, useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { calendarKeys, fetchCalendarMonth } from '../api'
import type { CalendarEvent } from '../api'
import { eventReminderIds, formatCN, formatWeekdayCN, parseKey, todayKey } from '../domain'
import { useCompleteReminder } from '../hooks/use-complete-reminder'
import { CalendarPanel, type CalendarView } from './CalendarPanel'
import { ToolDock } from './ToolDock'
import { AppNavbar } from '@/components/shared/AppNavbar'
import { PageFade } from '@/components/shared/PageFade'
import { useMediaQuery } from '@/hooks/use-media'
import { useToday } from '@/hooks/use-today'
import { errMessage } from '@/lib/errors'
import { InboxCard, QuickAdd } from './SideCards'
import { TodayCard } from './TodayCard'
import { AddReminderDialog } from './AddReminderDialog'
import { DaySheet } from './DaySheet'
import type { InboxItem } from '../types'

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
  // useToday 跨零点自动重算：整夜不关的工作台不会把「今天」冻结在昨天
  const todayDate = useToday()
  const today = useMemo(() => todayKey(todayDate), [todayDate])
  // 手机端抽屉口径：与本页 max-[760px]: 的 Tailwind 类一致（旧 isMobile() 读
  // innerWidth 瞬间值且无 resize 订阅，跨过断点后点日期不会开抽屉）
  const isMobile = useMediaQuery('(max-width: 760px)')
  const [sheetDay, setSheetDay] = useState<string | null>(null)
  // 新增安排弹窗（day=null 关闭）；由日历空白格与手机抽屉「＋新增」共同打开
  const [adding, setAdding] = useState<{ day: string; time: string } | null>(null)

  const todayParts = useMemo(() => {
    const d = parseKey(today)
    return { year: d.getFullYear(), month: d.getMonth() + 1 } // month 为 1-based（后端 calendar 接口契约）
  }, [today])
  // 日历视图月：0-based（JS Date 口径，与 CalendarPanel 的 buildMonthGrid / 头部显示一致）。
  // 注意别把上面 1-based 的 todayParts 直接当 view 用——两者差 1，混用会把 9 月渲染成 10 月。
  const [view, setView] = useState<CalendarView>(() => {
    const d = parseKey(today)
    return { year: d.getFullYear(), month: d.getMonth() }
  })

  /* 视图月日历（CalendarPanel 渲染 + 手机抽屉数据源）；今日月日历（统计 + 今日卡）。
     后端 month 参数是 1-based：view 的 0-based 月在查询边界 +1；view 与今天同月时
     两个 query key 相同，react-query 自动去重为一次请求。 */
  const viewQuery = useQuery({
    queryKey: calendarKeys.month(view.year, view.month + 1),
    queryFn: () => fetchCalendarMonth(view.year, view.month + 1),
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
  // 统计失败时这里仍是 0 兜底，但不再被当成真数据展示：问候行与今日卡
  // 在 todayQuery.isError 时改渲染错误占位（stats 只剩 CalendarPanel 头部在消费）
  const stats = useMemo(
    () => todayQuery.data?.stats ?? { today: 0, today_done: 0, deadline_in_7days: 0, month_court: 0 },
    [todayQuery.data],
  )
  // 后端已按「时间升序 + 紧要排前」排好，直接取
  const todayEvents = useMemo(() => todayEventsByDay[today] ?? [], [todayEventsByDay, today])

  const invalidateCalendar = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: calendarKeys.all })
  }, [queryClient])

  /* 勾选完成：合并事件要带全部 member_ids 下发（eventReminderIds 保证口径） */
  const completeMutation = useCompleteReminder()
  const handleToggleComplete = useCallback(
    (e: CalendarEvent) => {
      completeMutation.mutate({ ids: eventReminderIds(e), completed: !e.is_completed })
    },
    [completeMutation],
  )

  const openAddDialog = useCallback(
    (day: string) => {
      setAdding({ day, time: defaultTimeFor(day, today) })
    },
    [today],
  )

  const notify = useCallback((msg: string) => toast.info(msg), [])

  /* 日历点某天：桌面端只高亮，手机端开抽屉 */
  const handleSelectDay = useCallback((key: string) => {
    if (isMobile) setSheetDay(key)
  }, [isMobile])

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
      void navigate(`/material-prep/${id}`)
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
    const d = parseKey(today)
    setView({ year: d.getFullYear(), month: d.getMonth() }) // 0-based（JS Date 口径）
  }, [today])

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
                {todayQuery.isError ? (
                  /* 统计拉不到就不给全 0 假象：一行小标 + 重试出口（详见今日卡错误行） */
                  <span className="text-destructive">
                    今日统计加载失败
                    <button
                      type="button"
                      className="ml-1.5 cursor-pointer underline underline-offset-3"
                      onClick={() => void todayQuery.refetch()}
                    >
                      重试
                    </button>
                  </span>
                ) : (
                  <>
                    今天 <b className="font-semibold text-status-red">{stats.today}</b> 件事 ·{' '}
                    <b className="font-semibold text-status-red">{stats.deadline_in_7days}</b> 件紧要事项 7 日内到期 ·
                    本月还有 <b className="font-semibold">{stats.month_court}</b> 个庭期
                  </>
                )}
              </div>
            </div>
            <QuickAdd onAdded={invalidateCalendar} />
          </div>

          <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
            {/* 左：日历 + 工具 */}
            <div className="min-w-0">
              {viewQuery.isError ? (
                /* 视图月拉取失败：整块日历换错误条（占位旧数据/空格子都会被误读成「没安排」） */
                <div className="rounded-[14px] border border-destructive/30 bg-destructive/5 px-5 py-[90px] text-center text-sm text-destructive">
                  {errMessage(viewQuery.error, '日历加载失败')}
                  <button
                    type="button"
                    className="ml-3 cursor-pointer underline underline-offset-3"
                    onClick={() => void viewQuery.refetch()}
                  >
                    重试
                  </button>
                </div>
              ) : (
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
                  onToggleComplete={handleToggleComplete}
                />
              )}
              <ToolDock />
            </div>

            {/* 右：今日 + 待处理 */}
            <div className="flex min-w-0 flex-col gap-5">
              <TodayCard
                events={todayEvents}
                loading={todayQuery.isLoading}
                error={todayQuery.isError ? errMessage(todayQuery.error, '今日安排加载失败') : null}
                onRetry={() => void todayQuery.refetch()}
                onOpenEvent={handleOpenEvent}
                onToggleComplete={handleToggleComplete}
              />
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
        onToggleComplete={handleToggleComplete}
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
