import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  confirmInvoiceIntake,
  copyInvoiceToClipboard,
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
      // 确认后该行立刻从「待认领」消失（用户要求：处理过的就该走开）。
      // 但确认完最想做的下一件事是复制那个重命名后的发票，所以把复制入口
      // 挂在 toast 上——行消失不影响操作，也不占列表位置。
      if (res.invoice_id) {
        toast.success(res.message || '已绑定该项目', {
          action: {
            label: '复制发票',
            onClick: () => {
              void copyInvoiceToClipboard(res.invoice_id!)
                .then((r) => {
                  if (r.success && r.copied > 0) toast.success('发票已复制，微信对话框直接 ⌘V 粘贴发送')
                  else toast.error(r.reason || '复制失败，请到项目页手动下载')
                })
                .catch(() => toast.error('复制失败，请到项目页手动下载'))
            },
          },
          duration: 12000,
        })
      } else {
        toast.success(res.message || '已绑定该项目')
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
