import { useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Loader2, X } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { errMessage } from '@/lib/errors'
import {
  attachPaymentInvoice,
  contractInvoiceKeys,
  listContractInvoices,
  listContractPayments,
  parsePaymentImage,
  parsePaymentText,
} from '../../api'
import { autoAttachTarget, splitByAmountMatch } from './invoice-auto-link'
import {
  EMPTY_FORM,
  formFromDraft,
  formFromImageDraft,
  parseAmount,
  remainingLabel,
  validateForm,
  type PaymentForm,
} from './payment-form'
import { PaymentInvoiceZone } from './PaymentInvoiceZone'
import { PaymentPasteZone } from './PaymentPasteZone'

/**
 * 记收款弹窗：律师真实工作流的两个入口合一。
 *
 * 1. **粘到账凭据**（文字与图片同一入口，见 PaymentPasteZone）：银行到账短信
 *    直接粘文字；**网银电子回单截图直接 ⌘V** → 金额/日期/付款人/用途自动填好，
 *    人核对后保存。回单版式还会读大写金额并与小写互校，对不上就醒目提示。
 * 2. **发票随时能进来**（见 PaymentInvoiceZone）：钱没到也能先传——票挂合同名下，
 *    保存收款后一键关联到这笔收款；或保存后直接拖票挂这笔收款。
 *
 * 顺序是刻意的：先「记这笔钱进来了」，再「把票挂到这笔钱上」。发票区在收款
 * 保存前也**不再禁用**——先开票后付款与先付款后开票都顺。
 *
 * **只有一笔收款时不再要求人点「关联」**：合同下仅此一笔收款，池里待归属的票
 * 保存后自动挂进去（开票金额当场对上）。多笔收款才交还给人判断；挂错可在
 * 发票节里解绑重挂。
 */
export function PaymentDialog({
  open,
  contractId,
  fixedAmount,
  receivedAmount,
  onClose,
  onSaved,
}: {
  open: boolean
  contractId: number
  /** 合同固定金额（null = 未约定，不做额度提示） */
  fixedAmount: number | null
  /** 该合同已收合计（用于提示剩余可收） */
  receivedAmount: number
  onClose: () => void
  /** 保存成功后：刷新合同（收款列表 + 开票状态都在合同详情里） */
  onSaved: () => void
}) {
  const [raw, setRaw] = useState('')
  const [form, setForm] = useState<PaymentForm>(EMPTY_FORM)
  const [hints, setHints] = useState<string[]>([])
  const [parsing, setParsing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  /** 已粘贴/选中的回单图名（仅展示；图片本身不落库，只用来取字段） */
  const [imageName, setImageName] = useState<string | null>(null)
  /** 大小写金额冲突：不阻塞保存，但必须让人看见 */
  const [mismatch, setMismatch] = useState(false)

  /** 收款保存后的 id：拿到它，发票区就从「挂合同」切换到「挂这笔收款」 */
  const [paymentId, setPaymentId] = useState<number | null>(null)

  const reset = useCallback(() => {
    setRaw('')
    setForm(EMPTY_FORM)
    setHints([])
    setError(null)
    setPaymentId(null)
    setImageName(null)
    setMismatch(false)
  }, [])

  const close = useCallback(() => {
    reset()
    onClose()
  }, [reset, onClose])

  const setField = (k: keyof PaymentForm, v: string) => setForm((prev) => ({ ...prev, [k]: v }))

  const doParse = async () => {
    if (!raw.trim()) return
    setParsing(true)
    setError(null)
    try {
      const draft = await parsePaymentText(raw)
      setForm(formFromDraft(draft))
      setHints(draft.hints)
      if (!draft.amount) setError('没认出金额，请手动填写')
    } catch (e) {
      setError(errMessage(e, '识别失败，请手动填写'))
    } finally {
      setParsing(false)
    }
  }

  /**
   * 粘贴/选中一张图（回单截图或 PDF）→ 后端读字 → 回填表单。
   *
   * 「没认出字」与「链路失败」分开处理：后者是 toast.error（调不通），前者是
   * 表单上的提示（这张图没读出东西，去手填/重拍）。混在一起会把「服务没通」
   * 误报成「这张图糊了」，律师会反复重拍。
   */
  const doParseImage = async (file: File) => {
    setParsing(true)
    setError(null)
    setImageName(file.name)
    try {
      const draft = await parsePaymentImage(file)
      setForm(formFromImageDraft(draft))
      setHints(draft.hints)
      setMismatch(draft.amount_mismatch)
      // 图里读到的文字也贴回输入框：律师要手改某个字段时，原文就在上面可对照
      if (draft.text) setRaw(draft.text.slice(0, 2000))
      if (!draft.amount) {
        setError(draft.text ? '没认出金额，请手动填写' : '这张图没读出文字，请重拍或手动填写')
      } else if (draft.amount_mismatch) {
        toast.warning('回单上的大写与小写金额不一致，请核对原件')
      }
    } catch (e) {
      setImageName(null)
      toast.error(errMessage(e, '图片识别失败，请改用文字或手动填写'))
    } finally {
      setParsing(false)
    }
  }

  const clearImage = () => {
    setImageName(null)
    setMismatch(false)
    setHints([])
  }

  const qc = useQueryClient()

  const doSave = async () => {
    const reason = validateForm(form)
    if (reason) {
      setError(reason)
      return
    }
    setSaving(true)
    setError(null)
    try {
      const { savePayment } = await import('./payment-save')
      const saved = await savePayment(contractId, form)
      setPaymentId(saved.id)
      // 收款已落库：立刻刷新合同，律师不必等发票关联完才看到这笔钱
      onSaved()
      toast.success('收款已记录')
      await autoAttachPendingInvoices(saved.id)
    } catch (e) {
      setError(errMessage(e, '保存失败，请重试'))
    } finally {
      setSaving(false)
    }
  }

  /**
   * 只有一笔收款时，把池里待归属的票自动挂给它（律师不必再点一次「关联」）。
   *
   * 判定与拆分都在纯函数里（invoice-auto-link.ts），这里只负责调接口和提示；
   * 任何一步失败都不能影响「收款已记录」这个既成事实，所以整段包在自己的
   * try 里、失败只提示不抛。
   */
  const autoAttachPendingInvoices = async (newPaymentId: number) => {
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

      const { amountMismatch } = splitByAmountMatch(attached, parseAmount(form.amount))
      if (amountMismatch.length === 0 && failed.length === 0) {
        toast.success(`已自动关联 ${attached.length} 张发票（开票金额已对上）`)
      } else if (failed.length === 0) {
        toast.info(`已关联 ${attached.length} 张发票，其中 ${amountMismatch.length} 张金额与收款不同，可核对后调整`)
      } else {
        setError(`有 ${failed.length} 张发票未能自动关联：${failed.join('；')}`)
      }
      void qc.invalidateQueries({ queryKey: contractInvoiceKeys.all(contractId) })
      onSaved()
    } catch (e) {
      // 自动归属只是省一步，失败退回手动「关联」，不影响收款本身
      setError(errMessage(e, '自动关联发票失败，请点「关联」手动挂'))
    }
  }

  const remaining = remainingLabel(fixedAmount, receivedAmount)

  return (
    <Dialog open={open} onOpenChange={(v) => !v && close()}>
      {/* grid-cols-[minmax(0,1fr)]：DialogContent 是单列 auto grid，识别结果那行
          truncate 文本（nowrap）的 min-content 会把列撑到 658px，整个弹窗横向
          溢出、footer 被顶出可视区（表现为「识别后 UI 错乱、保存按钮够不着」）。
          minmax(0,…) 把列的 min 钳到 0，截断才真正生效。
          sm:max-w-[620px]：必须带 sm: 前缀才能覆盖基类的 sm:max-w-lg(512px)，
          裸 max-w-[620px] 会被 sm: 变体压制，弹窗一直偏窄。 */}
      <DialogContent className="max-h-[88vh] grid-cols-[minmax(0,1fr)] gap-0 overflow-y-auto p-6 sm:max-w-[620px]">
        <DialogHeader className="pb-3">
          <DialogTitle className="text-[15px]">记收款</DialogTitle>
        </DialogHeader>

        {/* ① 粘贴到账凭据：短信文字与回单图片同一入口（见 PaymentPasteZone） */}
        <PaymentPasteZone
          raw={raw}
          hints={hints}
          imageName={imageName}
          parsing={parsing}
          disabled={paymentId != null}
          onRawChange={setRaw}
          onParseText={() => void doParse()}
          onPickImage={(f) => void doParseImage(f)}
          onClearImage={clearImage}
        />

        {/* ② 核对并保存 */}
        <section className="grid grid-cols-2 gap-3 border-b border-border-light py-4">
          {mismatch && (
            /* 回单上大写与小写对不上：常见于 OCR 把小写读错一位（回单的大写金额
               是财务上更可信的一方）。不拦保存，但必须显眼，否则就成了「静默错账」。 */
            <div className="col-span-2 flex items-start gap-1.5 rounded-[8px] bg-status-yellow/12 px-2.5 py-2 text-[11.5px] text-status-yellow">
              <span className="mt-px flex-none">⚠</span>
              <span className="min-w-0 break-words">
                回单上的大写与小写金额不一致，请对照原件确认金额后再保存。
              </span>
            </div>
          )}
          <label className="flex flex-col gap-1">
            <span className="text-[12px] font-[600]">收款金额 *</span>
            <Input
              value={form.amount}
              onChange={(e) => setField('amount', e.target.value)}
              placeholder="9000"
              inputMode="decimal"
              className="tabular-nums"
              disabled={paymentId != null}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[12px] font-[600]">收款日期 *</span>
            <Input
              type="date"
              value={form.receivedAt}
              onChange={(e) => setField('receivedAt', e.target.value)}
              disabled={paymentId != null}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[12px] font-[600]">开票金额</span>
            <Input
              value={form.invoicedAmount}
              onChange={(e) => setField('invoicedAmount', e.target.value)}
              placeholder="先开过票可不填，保存后关联"
              inputMode="decimal"
              className="tabular-nums"
              disabled={paymentId != null}
            />
          </label>
          <div className="flex flex-col justify-end pb-1 text-[11px] text-muted-foreground">
            {remaining && (
              <span>
                合同剩余可收 <b className="tabular-nums">{remaining}</b>
              </span>
            )}
          </div>
          <label className="col-span-2 flex flex-col gap-1">
            <span className="text-[12px] font-[600]">备注</span>
            <Textarea
              value={form.note}
              onChange={(e) => setField('note', e.target.value)}
              rows={2}
              placeholder="付款人 / 用途 / 对应案件"
              className="text-[12.5px]"
              disabled={paymentId != null}
            />
          </label>
        </section>

        {/* ③ 发票：保存前挂合同（先开票），保存后挂这笔收款 + 一键关联 */}
        <PaymentInvoiceZone
          contractId={contractId}
          paymentId={paymentId}
          paymentAmount={parseAmount(form.amount)}
          onChanged={onSaved}
        />

        {error && (
          <div className="mt-3 flex items-start gap-1.5 rounded-[8px] bg-status-red/8 px-2.5 py-2 text-[11.5px] text-status-red">
            <X className="mt-px size-3.5 flex-none" />
            <span className="min-w-0 break-words">{error}</span>
          </div>
        )}

        <DialogFooter className="mt-4 gap-2">
          <Button variant="outline" onClick={close}>
            {paymentId == null ? '取消' : '完成'}
          </Button>
          {paymentId == null && (
            <Button onClick={() => void doSave()} disabled={saving}>
              {saving && <Loader2 className="size-3.5 animate-spin" />}
              保存收款
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
