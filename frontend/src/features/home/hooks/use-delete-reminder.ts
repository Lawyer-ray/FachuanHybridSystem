import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { calendarKeys, deleteReminders, type CalendarMonth } from '../api'
import { eventReminderIds } from '../domain'
import { errMessage } from '@/lib/errors'

/**
 * 删除日历事件。乐观更新：onMutate 先把缓存里各月中命中的事件移除（格子立刻
 * 少一条，不等网络往返）；失败回滚快照并把后端文案弹出来（403 时是
 * 「仅提醒创建人或管理员可以删除该提醒」），onSettled 再 invalidate 兜底——
 * stats 统计口径始终由后端重算保持权威。
 *
 * 调用方用 domain.ts 的 eventReminderIds(e) 取要下发的 id 集合：合并事件的
 * 全部成员一起删。入口按事件 can_delete 显隐，正常不会撞到 403。
 */
export function useDeleteReminder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ ids }: { ids: number[] }) => deleteReminders(ids),
    onMutate: async ({ ids }) => {
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
            (events ?? []).filter((e) => {
              // 命中口径与下发口径同源：eventReminderIds(e) 的任一成员被点名即视为该合并事件
              const hit = eventReminderIds(e).some((id) => idSet.has(id))
              if (hit) touched = true
              return !hit
            }),
          ]),
        )
        if (touched) queryClient.setQueryData(key, { ...data, days })
      }
      return { snapshots }
    },
    onError: (error, _vars, ctx) => {
      toast.error(errMessage(error, '删除失败，请稍后重试'))
      for (const [key, data] of ctx?.snapshots ?? []) queryClient.setQueryData(key, data)
    },
    onSuccess: () => {
      toast.success('已删除')
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: calendarKeys.all })
    },
  })
}
