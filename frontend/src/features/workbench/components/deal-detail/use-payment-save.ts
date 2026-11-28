/**
 * 记收款的**保存动作**：落库 → 立刻刷新合同 → 自动关联池里待归属的发票。
 *
 * 为什么从 PaymentDialog 拆出去：弹窗的一半是「表单与识别」（粘凭据、读回单、
 * 核对字段、大小写金额互校、放弃确认），另一半是「保存这一笔之后要连带做什么」——
 * 落库、拿新收款 id、两条 toast、逐张挂发票、发票缓存失效。后者是一串有顺序、
 * 有两层 try 兜底的异步编排，混在渲染里时最容易被误改（尤其是「自动关联失败
 * **不能**回滚『收款已记录』」这条）。拆出来后这段可以单独读、单独审。
 *
 * ═══ 三条不能动的语义 ═══
 * 1. **错误横幅是共用的**：解析错误、字段校验失败、保存/关联失败都落在弹窗的同一处
 *    横幅上，所以这里**不自带 error 状态**，读写全部走 `onError`（弹窗传 setError）。
 * 2. **收款落库即既成事实**：`setPaymentId` + `onSaved` + 「收款已记录」在自动
 *    关联之前就完成了；自动关联那层 try 失败只提示、绝不回滚。
 * 3. **`paymentId` 只有一份**（就是这里）：弹窗拿它驱动 6 处 disabled 与页脚
 *    文案。`reset` 只清它——它挂在弹窗的关闭路径上，语义与拆分前的
 *    `setPaymentId(null)` 完全一致（否则保存后关弹窗再打开，字段还是锁的）。
 */
import { useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { errMessage } from '@/lib/errors'

import {
  attachPaymentInvoice,
  contractInvoiceKeys,
  listContractInvoices,
  listContractPayments,
} from '../../api'
import { autoAttachTarget, splitByAmountMatch } from './invoice-auto-link'
import { parseAmount, type PaymentForm } from './payment-form'

export function usePaymentSave({
  contractId,
  amountText,
  onSaved,
  onError,
}: {
  contractId: number
  /** 当前表单里的收款金额（自动关联时与发票金额比对用） */
  amountText: string
  /** 保存成功 / 关联完成后的刷新回调（弹窗透传自己的 onSaved） */
  onSaved: () => void
  /** 失败与提醒写回弹窗那条共用横幅；传 null 即清空（弹窗透传 setError） */
  onError: (message: string | null) => void
}) {
  const qc = useQueryClient()
  const [saving, setSaving] = useState(false)
  /** 收款保存后的 id：拿到它，发票区就从「挂合同」切换到「挂这笔收款」 */
  const [paymentId, setPaymentId] = useState<number | null>(null)

  /** 清掉收款 id（弹窗关闭时 reset 用；只清这一个字段，别顺手清表单） */
  const reset = useCallback(() => setPaymentId(null), [])

  /**
   * 只有一笔收款时，把池里待归属的票自动挂给它（律师不必再点一次「关联」）。
   *
   * 判定与拆分都在纯函数里（invoice-auto-link.ts），这里只负责调接口和提示；
   * 任何一步失败都不能影响「收款已记录」这个既成事实，所以整段包在自己的
   * try 里、失败只提示不抛。
   */
  const autoAttachPendingInvoices = useCallback(
    async (newPaymentId: number) => {
      try {
        const [pool, payments] = await Promise.all([
          listContractInvoices(contractId, true),
          listContractPayments(contractId),
        ])
        const targetId = autoAttachTarget(payments, pool)
        if (targetId == null || targetId !== newPaymentId) return

        const attached = []
        const failed: string[] = []
        for (const inv of pool) {
          if (inv.payment_id != null) continue
          try {
            await attachPaymentInvoice(inv.id, targetId)
            attached.push(inv)
          } catch (e) {
            failed.push(`${inv.display_filename}：${errMessage(e, '关联失败')}`)
          }
        }
        if (!attached.length && !failed.length) return

        const { amountMismatch } = splitByAmountMatch(attached, parseAmount(amountText))
        if (amountMismatch.length === 0 && failed.length === 0) {
          toast.success(`已自动关联 ${attached.length} 张发票（开票金额已对上）`)
        } else if (failed.length === 0) {
          toast.info(`已关联 ${attached.length} 张发票，其中 ${amountMismatch.length} 张金额与收款不同，可核对后调整`)
        } else {
          onError(`有 ${failed.length} 张发票未能自动关联：${failed.join('；')}`)
        }
        void qc.invalidateQueries({ queryKey: contractInvoiceKeys.all(contractId) })
        onSaved()
      } catch (e) {
        // 自动归属只是省一步，失败退回手动「关联」，不影响收款本身
        onError(errMessage(e, '自动关联发票失败，请点「关联」手动挂'))
      }
    },
    [amountText, contractId, onError, onSaved, qc],
  )

  /** 保存这一笔收款（字段校验在弹窗里做，这里只收已经校验过的表单） */
  const save = useCallback(
    async (form: PaymentForm) => {
      setSaving(true)
      onError(null)
      try {
        const { savePayment } = await import('./payment-save')
        const saved = await savePayment(contractId, form)
        setPaymentId(saved.id)
        // 收款已落库：立刻刷新合同，律师不必等发票关联完才看到这笔钱
        onSaved()
        toast.success('收款已记录')
        await autoAttachPendingInvoices(saved.id)
      } catch (e) {
        onError(errMessage(e, '保存失败，请重试'))
      } finally {
        setSaving(false)
      }
    },
    [autoAttachPendingInvoices, contractId, onError, onSaved],
  )

  return { saving, paymentId, save, reset }
}
