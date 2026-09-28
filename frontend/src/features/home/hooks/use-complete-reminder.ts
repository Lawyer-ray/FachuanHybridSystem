import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { calendarKeys, setRemindersCompleted } from '../api'

/**
 * 勾选完成 / 取消完成。成功后失效全部日历 query（视图月 + 今日月两个
 * 缓存一起刷新，统计口径由后端统一算）。
 *
 * 调用方用 domain.ts 的 eventReminderIds(e) 取要下发的 id 集合，
 * 保证合并事件的全部成员一起更新。
 */
export function useCompleteReminder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ ids, completed }: { ids: number[]; completed: boolean }) =>
      setRemindersCompleted(ids, completed),
    onSuccess: (_updated, vars) => {
      toast.success(vars.completed ? '已标记完成' : '已恢复为未完成')
      void queryClient.invalidateQueries({ queryKey: calendarKeys.all })
    },
    onError: () => toast.error('标记失败，请稍后重试'),
  })
}
