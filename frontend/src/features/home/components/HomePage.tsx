import { useCallback, useMemo, useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'

import { calendarKeys, fetchCalendarMonth } from '../api'
import { formatCN, formatWeekdayCN, parseKey } from '../domain'
import { useEventActions } from '../hooks/use-event-actions'
import { CalendarPanel, type CalendarView } from './CalendarPanel'
import { EventContextMenu } from './EventContextMenu'
import { EventDetailDialog } from './EventDetailDialog'
import { ToolDock } from './ToolDock'
import { materialPrepDetail } from '@/app/paths'
import { useToday } from '@/hooks/use-today'
import { todayKey } from '@/lib/date'
import { errMessage } from '@/lib/errors'
import { ErrorBlock } from '@/components/shared/AsyncState'
import { InboxCard } from './InboxCard'
import { QuickAdd } from './QuickAdd'
import { PendingIntakeCard } from '@/features/payment-intake'
import { PendingInvoicesCard } from '@/features/invoice-intake'
import { CardHead } from '@/components/shared/CardHead'
import { PANEL } from '@/components/shared/panel-styles'
import { PendingSyncButton } from './PendingSyncButton'
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
  // 当日抽屉的开关口径：**日历密度**（手机视口或面板被助手并排 / 分屏压窄）。
  // 以前按视口 760px 判，助手并排把日历压到 ~80px 宽时视口仍很宽，格子里只剩
  // 一两个字的标题、点开却是「新增」弹窗，看不到该日详情。密度由 CalendarPanel
  // 按面板净宽算好回传（见 calendar-density.ts）。
  const [calendarCompact, setCalendarCompact] = useState(false)
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

  /* 事件级动作整包（详情弹窗 / 勾完成 / 删除 / 右键菜单）：见 hooks/use-event-actions.ts。
     传 viewEventsByDay 进去做快照保鲜用——**不是**再查一次日历，页面已经查过了。 */
  const { detail, closeDetail, ctxMenu, closeCtxMenu, openEvent, openCase, toggleComplete, deleteEvent, eventActions } =
    useEventActions(viewEventsByDay)

  const openAddDialog = useCallback(
    (day: string) => {
      setAdding({ day, time: defaultTimeFor(day, today) })
    },
    [today],
  )

  /* 日历点某天：窄日历（手机 / 面板被压窄）开当日抽屉，宽日历只高亮 */
  const handleSelectDay = useCallback((key: string) => {
    if (calendarCompact) setSheetDay(key)
  }, [calendarCompact])

  // 材料包 / 已转过的消息 → 直接进材料预处理的详情页。
  // 用 navigate 做 SPA 跳转，别用 window.location.assign（那是整页刷新，
  // 既丢状态也播不了过渡动画）。
  const navigate = useNavigate()
  const goPack = useCallback(
    (id: number) => {
      // 带 ?stage=todo：目标是材料包详情，不带 stage 时详情路由会回落成
      // 「收件箱」，打开瞬间先渲染一帧收件箱列表再被阅读器盖住（闪一下）。
      void navigate(`${materialPrepDetail(id)}?stage=todo`)
    },
    [navigate],
  )

  /* 收件箱点行：**不再跳收件箱列表**。
   *
   * 只有材料包（含早转过的消息）直接进阅读器——那时进去就是要看文档。
   * 其余全部就地展开（由 InboxCard 自己管展开态）：一张网告知书、判决书送达、
   * 邮件绝大多数是纯通知，读正文/下附件在侧栏里一步就能完成；而此前一律平转到
   * /material-prep，用户以为在看详情，落地却是一屏 300+ 条同质消息，还得靠标题
   * 再找一遍——法院送达里五条都叫「Attached Image」时根本无法区分。
   * 要横向浏览时走「查看全部」（CardHead 的 moreHref）。 */
  const handleInboxOpen = useCallback(
    (item: InboxItem) => {
      if (item.packId != null) goPack(item.packId)
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
    <>
      {/* 导航栏由 AppShell 常驻；入场过渡挂在 main 上，换页重挂才播一次。
          @container：布局断点改量 main 的净宽——AI 助手并排让位（padding-right）
          后视口断点量不到被吃掉的宽度，会把日历挤成窄条（详见 AppShell 并排注释） */}
      <main className="app-page-enter @container mx-auto max-w-[1920px] px-[32px] pt-[26px] pb-20 max-[760px]:px-[14px] max-[760px]:pt-[18px]">
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

        {/* 双栏阈值按容器净宽（1200 ≈ 旧视口 xl 1280 扣页边距）：助手让位后
            净宽不足即回落单栏，日历占满、右栏下移，不再被挤成窄条 */}
        <div className="grid grid-cols-1 items-start gap-6 @min-[1200px]:grid-cols-[minmax(0,1fr)_340px]">
          {/* 左：日历 + 工具。@container 让 ToolDock / 日历密度按本栏宽度自适应 */}
          <div className="@container min-w-0">
            {viewQuery.isError ? (
              /* 视图月拉取失败：整块日历换错误条（占位旧数据/空格子都会被误读成「没安排」）。
                 竖直留白与日历卡相当，避免错误条把下方工具坞顶上去了 */
              <ErrorBlock
                error={viewQuery.error}
                fallback="日历加载失败"
                retryText="重试"
                onRetry={() => void viewQuery.refetch()}
                className="rounded-[14px] px-5 py-[90px] text-sm"
              />
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
                onOpenAdd={openAddDialog}
                eventActions={eventActions}
                // 密度回传：窄日历改成「点格开当日抽屉」，宽日历保持「点空白新增」
                onCompactChange={setCalendarCompact}
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
              onOpenEvent={openEvent}
              onToggleComplete={toggleComplete}
            />
            {/* 待认领（款项 + 发票）：财务给我发了东西、等我确认，比消息优先级高，放收件箱之上。

                **一个外壳两张卡内容**（用户要求"节约空间"）：外层 section + CardHead 由
                首页提供，两个 feature 各自以 bare 模式只渲染内容区与自己的分组标题。
                这样两个 feature 互不 import（守住 feature 隔离），视觉上却是一张卡。

                常驻渲染（无待办时显示空态）——用户要求每次进首页都能看到。 */}
            <section className={`${PANEL} overflow-hidden`}>
              {/* 同步按钮放卡头右上：卡变空态时这里是唯一能主动拉取新到账/发票的出口，
                  否则用户只能等后台定时任务或绕去收件箱页点同步。 */}
              <CardHead title="待认领" action={<PendingSyncButton />} />
              <PendingIntakeCard bare />
              <PendingInvoicesCard bare />
            </section>
            <InboxCard onOpen={handleInboxOpen} onOpenPack={goPack} />
          </div>
        </div>
      </main>

      {/* 手机端当日安排抽屉 */}
      <DaySheet
        day={sheetDay}
        today={today}
        events={sheetDay ? (viewEventsByDay[sheetDay] ?? []) : []}
        onClose={() => setSheetDay(null)}
        onOpenEvent={openEvent}
        onToggleComplete={toggleComplete}
        onAdd={() => sheetDay && openAddDialog(sheetDay)}
      />

      {/* 新增安排弹窗：日历空白格 / 手机抽屉「＋新增」共用 */}
      <AddReminderDialog
        day={adding?.day ?? null}
        defaultTime={adding?.time ?? '09:00'}
        onClose={() => setAdding(null)}
        onSaved={invalidateCalendar}
      />

      {/* 事件详情弹窗：日历格 / 手机抽屉 / 今日卡共用（z-[130]，叠在 z-61 的抽屉之上）。
          编辑保存后 invalidate 重取日历（事件可能挪了日子 / 月份） */}
      <EventDetailDialog
        event={detail}
        onClose={closeDetail}
        onSaved={invalidateCalendar}
        onOpenCase={openCase}
        onToggleComplete={toggleComplete}
        onDelete={deleteEvent}
      />

      {/* 日历事件右键快捷菜单（标记完成 / 删除） */}
      <EventContextMenu
        target={ctxMenu}
        onClose={closeCtxMenu}
        onToggleComplete={toggleComplete}
        onDelete={deleteEvent}
      />
    </>
  )
}
