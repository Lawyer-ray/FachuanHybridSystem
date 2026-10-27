import { useCallback, useState } from 'react'
import { Loader2, Sparkles, X } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { errMessage } from '@/lib/errors'
import { parsePaymentText } from '../../api'
import { EMPTY_FORM, formFromDraft, parseAmount, remainingLabel, validateForm, type PaymentForm } from './payment-form'
import { PaymentInvoiceZone } from './PaymentInvoiceZone'

/**
 * 记收款弹窗：律师真实工作流的两个入口合一。
 *
 * 1. **粘一段银行到账短信** → 点「识别」→ 金额/日期/付款人/用途自动填好，人核对后保存。
 * 2. **发票随时能进来**（见 PaymentInvoiceZone）：钱没到也能先传——票挂合同名下，
 *    保存收款后一键核销；或保存后直接拖票挂这笔收款。
 *
 * 顺序是刻意的：先「记这笔钱进来了」，再「把票核销到这笔钱」。发票区在收款
 * 保存前也**不再禁用**——先开票后付款与先付款后开票都顺。
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

  /** 收款保存后的 id：拿到它，发票区就从「挂合同」切换到「挂这笔收款」 */
  const [paymentId, setPaymentId] = useState<number | null>(null)

  const reset = useCallback(() => {
    setRaw('')
    setForm(EMPTY_FORM)
    setHints([])
    setError(null)
    setPaymentId(null)
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
      // 收款已落库：立刻刷新合同，律师不必等发票核销完才看到这笔钱
      onSaved()
      toast.success('收款已记录')
    } catch (e) {
      setError(errMessage(e, '保存失败，请重试'))
    } finally {
      setSaving(false)
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

        {/* ① 粘贴到账短信 */}
        <section className="border-b border-border-light pb-4">
          <div className="mb-1.5 flex items-baseline gap-2">
            <span className="text-[12px] font-[650]">粘贴到账短信</span>
            <span className="text-[11px] text-muted-foreground">（银行 App 的通知原样粘进来即可）</span>
          </div>
          <Textarea
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            placeholder="【建设银行】某某公司10月15日17时5分向贵公司4501账户律师费存入人民币9000元。"
            rows={3}
            className="text-[12.5px]"
            disabled={paymentId != null}
          />
          <div className="mt-2 flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => void doParse()} disabled={parsing || !raw.trim() || paymentId != null}>
              {parsing ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
              识别
            </Button>
            {hints.length > 0 && (
              <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground" title={hints.join(' · ')}>
                {hints.join(' · ')}
              </span>
            )}
          </div>
        </section>

        {/* ② 核对并保存 */}
        <section className="grid grid-cols-2 gap-3 border-b border-border-light py-4">
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

        {/* ③ 发票：保存前挂合同（先开票），保存后挂这笔收款 + 一键核销 */}
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
