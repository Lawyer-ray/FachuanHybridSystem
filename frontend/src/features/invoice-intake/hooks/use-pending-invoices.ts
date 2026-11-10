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
 * 成功后不弹 toast action 而是把结果回调给调用方（`onConfirmed`）：确认完最想做
 * 的下一件事是复制那个重命名后的发票，而「复制」需要一个可见的落点。把刚确认的
 * 行**就地留在列表里**（换成「文件名 + 复制」形态）比弹一个会消失的 toast 更好用。
 *
 * 留下的只是**前端内存态**：刷新页面即消失，不会在库里堆积。
 */
export function useConfirmInvoiceIntake(options?: {
  /** 确认成功：把结果交给调用方渲染“已完成”行 */
  onConfirmed?: (payload: { intakeId: number; invoiceId: number; displayFilename: string; message: string }) => void
}) {
  const invalidate = useInvalidateInvoices()
  return useMutation({
    mutationFn: ({ id, contractId, paymentId }: { id: number; contractId?: number; paymentId?: number }) =>
      confirmInvoiceIntake(id, contractId, paymentId),
    onSuccess: (res) => {
      invalidate()
      toast.success(res.message || '已绑定该项目')
      if (res.invoice_id) {
        options?.onConfirmed?.({
          intakeId: res.intake_id,
          invoiceId: res.invoice_id,
          displayFilename: res.invoice_display_filename ?? '',
          message: res.message || '已绑定该项目',
        })
      }
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
