import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  confirmInvoiceIntake,
  getPendingInvoiceCount,
  INVOICE_INTAKE_COUNT_KEY,
  INVOICE_INTAKE_PENDING_KEY,
  listPendingInvoices,
  rejectInvoiceIntake,
  reopenInvoiceIntake,
} from '../api'
import { errMessage } from '@/lib/errors'

/** 首页「待认领发票」模块的数据源。 */
export function usePendingInvoices(limit = 20) {
  return useQuery({
    queryKey: [...INVOICE_INTAKE_PENDING_KEY, limit],
    queryFn: () => listPendingInvoices(limit),
    staleTime: 30_000,
  })
}

/** 首页角标计数（不拉全量）。 */
export function usePendingInvoiceCount() {
  return useQuery({
    queryKey: INVOICE_INTAKE_COUNT_KEY,
    queryFn: getPendingInvoiceCount,
    staleTime: 30_000,
  })
}

/** 任何会改变待办集合的操作后统一刷新列表与角标。 */
function useInvalidateInvoices() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: INVOICE_INTAKE_PENDING_KEY })
    void queryClient.invalidateQueries({ queryKey: INVOICE_INTAKE_COUNT_KEY })
  }
}

/**
 * 确认绑定。
 *
 * 成功后必须提示「已绑定到项目」——这是财务动作，用户要明确知道这张票
 * 落到哪个项目上了，而不是只看到列表少了一条。
 */
export function useConfirmInvoiceIntake() {
  const invalidate = useInvalidateInvoices()
  return useMutation({
    mutationFn: ({ id, contractId, paymentId }: { id: number; contractId?: number; paymentId?: number }) =>
      confirmInvoiceIntake(id, contractId, paymentId),
    onSuccess: (res) => {
      invalidate()
      toast.success(res.message || '已绑定该项目')
    },
    onError: (error) => toast.error(errMessage(error, '确认失败')),
  })
}

export function useRejectInvoiceIntake() {
  const invalidate = useInvalidateInvoices()
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => rejectInvoiceIntake(id, reason),
    onSuccess: (res) => {
      invalidate()
      toast.success(res.message || '已标记为无关发票')
    },
    onError: (error) => toast.error(errMessage(error, '操作失败')),
  })
}

export function useReopenInvoiceIntake() {
  const invalidate = useInvalidateInvoices()
  return useMutation({
    mutationFn: (id: number) => reopenInvoiceIntake(id),
    onSuccess: (res) => {
      invalidate()
      toast.success(res.message || '已撤销')
    },
    onError: (error) => toast.error(errMessage(error, '撤销失败')),
  })
}
