import { useCallback, useRef, useState } from 'react'
import { Loader2, Sparkles, Upload, X } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { errMessage } from '@/lib/errors'
import { parsePaymentText, uploadPaymentInvoices, type PaymentInvoice } from '../../api'
import { EMPTY_FORM, formFromDraft, remainingLabel, validateForm, type PaymentForm } from './payment-form'

/**
 * 记收款弹窗：两个入口合一，都是律师真实的工作流。
 *
 * 1. **粘一段银行到账短信** → 点「识别」→ 金额/日期/付款人/用途自动填好，人核对后保存。
 * 2. **拖发票进来** → 逐张识别落盘，自动回填开票金额与开票状态。
 *
 * 顺序是刻意的：先「记这笔钱进来了」，再「把票归到这个合同」。发票区在收款
 * 保存后禁用——`Invoice` 必须挂在某条 `ContractPayment` 上，没落收款就无处可挂。
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

  /** 收款保存后的 id：发票区只有拿到它才可用 */
  const [paymentId, setPaymentId] = useState<number | null>(null)
  const [invoices, setInvoices] = useState<PaymentInvoice[]>([])
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const reset = useCallback(() => {
    setRaw('')
    setForm(EMPTY_FORM)
    setHints([])
    setError(null)
    setPaymentId(null)
    setInvoices([])
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
      setInvoices(saved.invoices)
      // 收款已落库：立刻刷新合同，律师不必等发票传完才看到这笔钱
      onSaved()
      toast.success('收款已记录')
    } catch (e) {
      setError(errMessage(e, '保存失败，请重试'))
    } finally {
      setSaving(false)
    }
  }

  const doUpload = async (files: File[]) => {
    if (!paymentId || files.length === 0) return
    setUploading(true)
    setError(null)
    try {
      const result = await uploadPaymentInvoices(paymentId, files)
      setInvoices((prev) => [...result.saved, ...prev])
      if (result.failed.length) {
        setError(result.failed.map((f) => `${f.filename}：${f.reason}`).join('；'))
      }
      if (result.duplicated_count > 0) {
        toast.warning(`${result.duplicated_count} 张发票号已存在，未重复计入开票金额`)
      }
      if (result.saved.length) {
        toast.success(`已识别并保存 ${result.saved.length} 张发票`)
        onSaved()
      }
    } catch (e) {
      setError(errMessage(e, '发票上传失败，请重试'))
    } finally {
      setUploading(false)
    }
  }

  const remaining = remainingLabel(fixedAmount, receivedAmount)

  return (
    <Dialog open={open} onOpenChange={(v) => !v && close()}>
      <DialogContent className="max-h-[88vh] max-w-[620px] gap-0 overflow-y-auto p-6">
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
              placeholder="未开票留空"
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

        {/* ③ 拖发票进来 */}
        <section className="pt-4">
          <div className="mb-1.5 flex items-baseline gap-2">
            <span className="text-[12px] font-[650]">发票</span>
            <span className="text-[11px] text-muted-foreground">
              {paymentId == null ? '先保存收款，再拖发票进来' : '拖入或点击上传，自动识别并归档到合同文件夹'}
            </span>
          </div>
          <div
            role="button"
            tabIndex={0}
            onClick={() => paymentId != null && fileRef.current?.click()}
            onKeyDown={(e) => e.key === 'Enter' && paymentId != null && fileRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              if (paymentId != null) e.currentTarget.dataset.drag = '1'
            }}
            onDragLeave={(e) => delete e.currentTarget.dataset.drag}
            onDrop={(e) => {
              e.preventDefault()
              delete e.currentTarget.dataset.drag
              const files = Array.from(e.dataTransfer.files)
              if (files.length) void doUpload(files)
            }}
            className={
              'flex flex-col items-center gap-1 rounded-[10px] border border-dashed py-5 text-[12px] transition-colors ' +
              (paymentId == null
                ? 'cursor-not-allowed border-border bg-secondary/30 text-muted-foreground/60'
                : 'cursor-pointer border-border hover:border-ring/50 hover:bg-secondary/40 data-[drag]:border-foreground data-[drag]:bg-secondary')
            }
          >
            {uploading ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : <Upload className="size-4 text-muted-foreground" />}
            <span>{uploading ? '正在识别发票…' : '把发票拖到这里，或点击选择'}</span>
            <span className="text-[10.5px] text-muted-foreground/70">支持 PDF / JPG / PNG，单张 ≤ 20MB</span>
          </div>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png"
            className="hidden"
            onChange={(e) => {
              const files = Array.from(e.target.files ?? [])
              e.target.value = ''
              if (files.length) void doUpload(files)
            }}
          />

          {invoices.length > 0 && (
            <ul className="mt-2 flex flex-col gap-1">
              {invoices.map((inv) => (
                <li key={inv.id} className="flex items-baseline gap-2 rounded-[6px] bg-secondary/50 px-2 py-1 text-[11.5px]">
                  <span className="min-w-0 flex-1 truncate" title={inv.display_filename}>
                    {inv.display_filename}
                  </span>
                  <span className="font-[620] tabular-nums">{inv.total_amount ? '¥' + inv.total_amount : '金额未识别'}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

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
