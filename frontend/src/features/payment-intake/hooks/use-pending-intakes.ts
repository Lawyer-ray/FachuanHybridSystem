import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  confirmIntake,
  getPendingCount,
  ignoreIntake,
  INTAKE_COUNT_KEY,
  INTAKE_PENDING_KEY,
  listPendingIntakes,
  rejectIntake,
  reopenIntake,
} from '../api'
import { errMessage } from '@/lib/errors'

/** 首页「待认领款项」模块的数据源。 */
export function usePendingIntakes(limit = 20) {
  return useQuery({
    queryKey: [...INTAKE_PENDING_KEY, limit],
    queryFn: () => listPendingIntakes(limit),
    staleTime: 30_000,
  })
}

/** 首页角标计数（不拉全量）。 */
export function usePendingIntakeCount() {
  return useQuery({
    queryKey: INTAKE_COUNT_KEY,
    queryFn: getPendingCount,
    staleTime: 30_000,
  })
}

/** 任何会改变待办集合的操作后统一刷新列表与角标。 */
function useInvalidateIntakes() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: INTAKE_PENDING_KEY })
    void queryClient.invalidateQueries({ queryKey: INTAKE_COUNT_KEY })
  }
}

/**
 * 确认归属。
 *
 * 成功后**必须提示已写入收款记录**——这是财务动作，用户要明确知道钱已经
 * 落到项目上了，而不是只看到列表少了一条。
 */
export function useConfirmIntake() {
  const invalidate = useInvalidateIntakes()
  return useMutation({
    mutationFn: ({ id, contractId, note }: { id: number; contractId?: number; note?: string }) =>
      confirmIntake(id, contractId, note),
    onSuccess: (res) => {
      invalidate()
      toast.success(res.message || '已确认并写入收款记录')
    },
    onError: (error) => toast.error(errMessage(error, '确认失败')),
  })
}

export function useRejectIntake() {
  const invalidate = useInvalidateIntakes()
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => rejectIntake(id, reason),
    onSuccess: (res) => {
      invalidate()
      toast.success(res.message || '已标记为非记账事件')
    },
    onError: (error) => toast.error(errMessage(error, '操作失败')),
  })
}

export function useIgnoreIntake() {
  const invalidate = useInvalidateIntakes()
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => ignoreIntake(id, reason),
    onSuccess: (res) => {
      invalidate()
      toast.success(res.message || '已标记为不需记账')
    },
    onError: (error) => toast.error(errMessage(error, '操作失败')),
  })
}

export function useReopenIntake() {
  const invalidate = useInvalidateIntakes()
  return useMutation({
    mutationFn: (id: number) => reopenIntake(id),
    onSuccess: (res) => {
      invalidate()
      toast.success(res.message || '已撤销')
    },
    onError: (error) => toast.error(errMessage(error, '撤销失败')),
  })
}
