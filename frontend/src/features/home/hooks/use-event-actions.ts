import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import type { CalendarEvent } from '../api'
import { eventReminderIds } from '../domain'
import { useCompleteReminder } from './use-complete-reminder'
import { useDeleteReminder } from './use-delete-reminder'

/** 右键菜单目标：事件 + 光标视口坐标（菜单 fixed 定位用） */
export interface EventContextMenuTarget {
  event: CalendarEvent
  x: number
  y: number
}

/**
 * 日历**事件级动作**整包：详情弹窗态 / 勾完成 / 删除 / 右键菜单。
 *
 * 为什么从 HomePage 拆出来：HomePage 的职责是「页面怎么排、数据怎么取」
 * （视图月、两个 month 查询、右栏卡片编排）；而这一组是「对单条安排做什么事」——
 * 打开哪条详情、确认后怎么下发 mutation、右键菜单点在哪。两者关注点不同，
 * 混在一起时页面组件被交互细节淹没（详情弹窗的快照保鲜尤其难读）。
 *
 * ═══ 两条不能动的约束 ═══
 * 1. `eventActions` 必须 useMemo 固化引用：CalendarPanel → DayCell → DayEventRow
 *    全套都套了 memo，对象每次重建就等于没 memo。所以它的 deps 只放三个
 *    useCallback；**绝不要**把 eventsByDay 塞进去——日历每次查询刷新都会击穿
 *    整个日历格的 memo，翻月/轮询时全表重渲。
 * 2. `eventsByDay` 由**调用方**传入（页面已经为渲染查过同一个视图月），这里
 *    不再自己 useQuery：同一个 /calendar 打两次既浪费又可能拿到两份不同快照。
 */
export function useEventActions(eventsByDay: Record<string, CalendarEvent[]>) {
  /* 事件详情弹窗：日历格（桌面）、手机当日抽屉、今日卡三个入口共用一个。
     以前只挂在 CalendarPanel 内部，手机端根本进不了日历格的事件行（只有圆点），
     抽屉里点事项又只是 toast——窄屏上详情 / 勾完成 / 删除全都够不着。 */
  const [detail, setDetail] = useState<CalendarEvent | null>(null)
  // 快照保鲜：勾选 / 删除后 invalidate 重取，eventsByDay 换新对象时用同 id 的
  // 新事件替换 detail 里的旧快照——否则弹窗停留在勾选前的完成态（网格刷新了、弹窗没跟上）
  useEffect(() => {
    setDetail((prev) => {
      if (!prev) return prev
      const fresh = (eventsByDay[prev.day] ?? []).find((e) => e.id === prev.id)
      return fresh && fresh !== prev ? fresh : prev
    })
  }, [eventsByDay])
  const closeDetail = useCallback(() => setDetail(null), [])
  const openEvent = useCallback((e: CalendarEvent) => setDetail(e), [])
  // 详情弹窗里的「打开案件」：案件详情页尚未实现，先给提示（按钮在无 case_id 时自身已禁用）
  const openCase = useCallback((e: CalendarEvent) => {
    toast.info(e.case_id ? `打开案件 #${e.case_id}：${e.title}` : '这条安排还没关联案件，可到「案件台账」里查看')
  }, [])

  /* 勾选完成：合并事件要带全部 member_ids 下发（eventReminderIds 保证口径）。
     依赖取 mutate（useMutation 里引用稳定），别依赖整个 mutation 结果对象——
     它每次渲染都换新引用，会让 useCallback 白做、连带击穿日历格的 memo */
  const completeMutation = useCompleteReminder()
  const { mutate: completeMutate } = completeMutation
  const toggleComplete = useCallback(
    (e: CalendarEvent) => {
      completeMutate({ ids: eventReminderIds(e), completed: !e.is_completed })
    },
    [completeMutate],
  )

  /* 删除：同样全量下发 member_ids；入口按后端 can_delete 显隐（谁创建谁删）。
     先关弹窗再下发——乐观移除 + 失败回滚由 hook 负责，弹窗停留会让已消失的事件看起来还"开着" */
  const deleteMutation = useDeleteReminder()
  const { mutate: deleteMutate } = deleteMutation
  const deleteEvent = useCallback(
    (e: CalendarEvent) => {
      setDetail(null)
      deleteMutate({ ids: eventReminderIds(e) })
    },
    [deleteMutate],
  )

  /* 右键事件行的快捷菜单（标记完成 / 直接删除）：删除走同一个 mutation，
     详情弹窗没开时 setDetail(null) 是 no-op */
  const [ctxMenu, setCtxMenu] = useState<EventContextMenuTarget | null>(null)
  const closeCtxMenu = useCallback(() => setCtxMenu(null), [])
  const handleEventContextMenu = useCallback((event: CalendarEvent, pos: { x: number; y: number }) => {
    setCtxMenu({ event, ...pos })
  }, [])

  /* 事件级动作整包（详情 / 勾完成 / 右键菜单）：日历三层只传这一个对象。
     必须 useMemo 固化引用——CalendarPanel → DayCell → DayEventRow 都套了 memo，
     对象每次重建就等于没 memo。 */
  const eventActions = useMemo(
    () => ({
      onOpenEvent: openEvent,
      onToggleComplete: toggleComplete,
      onEventContextMenu: handleEventContextMenu,
    }),
    [openEvent, toggleComplete, handleEventContextMenu],
  )

  return {
    detail,
    closeDetail,
    ctxMenu,
    closeCtxMenu,
    openEvent,
    openCase,
    toggleComplete,
    deleteEvent,
    eventActions,
  }
}
