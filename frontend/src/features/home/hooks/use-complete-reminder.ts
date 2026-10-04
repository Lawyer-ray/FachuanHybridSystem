import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { calendarKeys, setRemindersCompleted, type CalendarMonth } from '../api'
import { eventReminderIds } from '../domain'

/**
 * 勾选完成 / 取消完成。乐观更新：onMutate 先把缓存里的日历月中目标事件的
 * is_completed 立即翻转（复选框即时可见，不等网络往返）；失败回滚快照，
 * onSettled 再 invalidate 兜底——stats 统计口径始终由后端重算保持权威。
 *
 * 调用方用 domain.ts 的 eventReminderIds(e) 取要下发的 id 集合，
 * 保证合并事件的全部成员一起更新。
 */
export function useCompleteReminder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ ids, completed }: { ids: number[]; completed: boolean }) =>
      setRemindersCompleted(ids, completed),
    onMutate: async ({ ids, completed }) => {
      // 停掉在途重拉，避免乐观态刚写入就被旧响应覆盖
      await queryClient.cancelQueries({ queryKey: calendarKeys.all })
      const snapshots = queryClient.getQueriesData<CalendarMonth>({ queryKey: calendarKeys.all })
      const idSet = new Set(ids)
      for (const [key, data] of snapshots) {
        if (!data?.days) continue
        let touched = false
        const days = Object.fromEntries(
          Object.entries(data.days).map(([dateKey, events]) => [
            dateKey,
            (events ?? []).map((e) => {
              // 命中口径与下发口径同源：eventReminderIds(e) 的任一成员被点名即视为该合并事件
              const hit = eventReminderIds(e).some((id) => idSet.has(id))
              if (!hit || e.is_completed === completed) return e
              touched = true
              return { ...e, is_completed: completed }
            }),
          ]),
        )
        if (touched) queryClient.setQueryData(key, { ...data, days })
      }
      return { snapshots }
    },
    onError: (_error, _vars, ctx) => {
      toast.error('标记失败，请稍后重试')
      for (const [key, data] of ctx?.snapshots ?? []) queryClient.setQueryData(key, data)
    },
    onSuccess: (_updated, vars) => {
      toast.success(vars.completed ? '已标记完成' : '已恢复为未完成')
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: calendarKeys.all })
    },
  })
}
