import { Check, Copy, ExternalLink, FileText, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { copyInvoiceToClipboard } from '../api'
import { formatAmount, MATCH_KIND_STYLES } from '../constants'
import { canConfirm, invoiceHeadline, topKind } from '../domain'
import type { InvoiceIntake } from '../types'
import { PaymentCompare, Section } from './PaymentCompare'
import { BTN_PRIMARY } from '@/components/shared/panel-styles'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

/**
 * 发票详情弹窗 —— 回答律师点开详情时真正的三个疑问：
 *
 * 1. **这张票是真的吗？** → 备注栏原文 + 原始文件名 + 跳邮件看原件
 * 2. **系统凭什么说是这个案子的？** → 匹配依据逐条（不是合成一句话）
 * 3. **钱对得上吗？** → 收款对照（见 PaymentCompare）
 *
 * 刻意**不重复列表里已有的信息**：金额/购买方/建议合同在行内已经看过，
 * 详情再列一遍就是浪费一次点击。这里只放列表看不到的东西。
 *
 * 金额与发票号码一律**只读**：PDF 里的数字是税局权威数据，系统里改一个和原件
 * 不符的数字，对账时会变成谁也说不清的坏账。识别错了应该重传原件。
 */
export function InvoiceDetailDialog({
  intake,
  open,
  onClose,
  onConfirm,
  busy,
}: {
  intake: InvoiceIntake | null
  open: boolean
  onClose: () => void
  onConfirm: (intake: InvoiceIntake) => void
  busy: boolean
}) {
  const navigate = useNavigate()
  const [copying, setCopying] = useState(false)

  if (!intake) return null

  const kind = topKind(intake)
  const kindStyle = kind ? MATCH_KIND_STYLES[kind] : null
  const confirmed = intake.status === 'confirmed'

  const doCopy = async () => {
    if (!intake.invoice_id || copying) return
    setCopying(true)
    try {
      const res = await copyInvoiceToClipboard(intake.invoice_id)
      if (res.success && res.copied > 0) toast.success('发票已复制，微信对话框直接 ⌘V 粘贴发送')
      else toast.error(res.reason || '复制失败，请改用下载')
    } catch (e) {
      toast.error(errMessage(e, '复制失败'))
    } finally {
      setCopying(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="grid-cols-[minmax(0,1fr)] gap-0 p-0 sm:max-w-[540px]">
        <DialogHeader className="px-5 pt-5 pb-3">
          <DialogTitle className="text-[15px]">发票详情</DialogTitle>
        </DialogHeader>

        {/* 抬头：金额大字 + 号码，一眼对上"是哪张票" */}
        <div className="flex items-baseline gap-2 px-5 pb-3">
          <span className="text-[22px] leading-none font-semibold tabular-nums">
            {intake.total_amount ? formatAmount(intake.total_amount) : '金额未识别'}
          </span>
          <span className="ml-auto truncate font-mono text-[10.5px] text-muted-foreground" title={intake.invoice_number}>
            {intake.invoice_number || '号码未识别'}
          </span>
        </div>
        <div className="px-5 pb-3 text-[11.5px] text-muted-foreground">
          {intake.invoice_date ?? '日期未识别'} 开具 · 购买方 {intake.buyer_name || '未识别'}
          {intake.project_code && (
            <span className="ml-2 rounded-[4px] bg-secondary px-1.5 py-[1px] font-mono text-[10px]">
              {intake.project_code}
            </span>
          )}
        </div>

        {/* 备注栏原文：案由全文（列表里被截断，这里给完整） */}
        {intake.remark && (
          <Section title="备注栏原文">
            <div className="rounded-[6px] bg-secondary/50 px-2 py-1.5 text-[11.5px] leading-[1.5] break-words">
              {intake.remark}
            </div>
          </Section>
        )}

        {/* 匹配依据：逐条列，不合成一句话——"为什么这么想"正是详情存在的价值 */}
        <Section title="匹配依据">
          <div className="flex items-center gap-1.5">
            {kindStyle && (
              <span className={cn('rounded-[99px] border px-[7px] py-[1px] text-[10px] font-semibold', kindStyle.chip)}>
                {kindStyle.label}
              </span>
            )}
            <span className="min-w-0 truncate text-[12px] font-medium">
              {intake.suggested_contract_name ?? '无可匹配的在办项目'}
            </span>
          </div>
          {intake.candidates[0]?.reasons.length ? (
            <ul className="mt-[5px] flex flex-col gap-[2px] pl-3">
              {intake.candidates[0].reasons.map((r) => (
                <li key={r} className="text-[11px] text-secondary-foreground">
                  · {r}
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-[4px] text-[11px] text-muted-foreground">{invoiceHeadline(intake)}</div>
          )}
          {intake.candidates[0]?.caveat && (
            <div className="mt-[4px] text-[10.5px] text-status-yellow">{intake.candidates[0].caveat}</div>
          )}
        </Section>

        <PaymentCompare intake={intake} />

        {/* 结果：已确认时给文件名、落点与复制；未确认时说明会落到哪 */}
        {confirmed ? (
          <Section title="已生成发票">
            <div className="flex items-start gap-1.5">
              <FileText className="mt-[2px] h-3.5 w-3.5 flex-none text-muted-foreground" aria-hidden />
              <span className="min-w-0 flex-1 break-all text-[11.5px]">
                {intake.invoice_display_filename || '发票已生成'}
              </span>
            </div>
            {intake.invoice_folder_subpath && (
              <div className="mt-[4px] pl-5 text-[10.5px] break-all text-muted-foreground">
                已归档到：{intake.invoice_folder_subpath}
              </div>
            )}
            <button
              type="button"
              disabled={copying}
              onClick={() => void doCopy()}
              className={cn(BTN_PRIMARY, 'mt-2 h-[28px] w-full')}
            >
              {copying ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
              复制发票
            </button>
          </Section>
        ) : null}

        {/* 原始文件 + 去看原件（跳收件箱那封邮件，那里有财务的话和附件预览） */}
        <Section title="原始文件">
          <div className="font-mono text-[10.5px] break-all text-muted-foreground">
            {intake.original_filename || '未记录'}
          </div>
          <button
            type="button"
            onClick={() => {
              onClose()
              void navigate(`/material-prep?message=${intake.inbox_message_id}`)
            }}
            className="mt-2 flex items-center gap-1 rounded-[6px] text-[11.5px] text-secondary-foreground underline-offset-3 hover:underline"
          >
            <ExternalLink className="h-3 w-3" aria-hidden />
            查看发票原件（跳转到原始邮件）
          </button>
        </Section>

        {/* 底部动作：未确认才给确认入口，口径与行内按钮完全一致 */}
        <div className="flex items-center gap-2 border-t border-border/70 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="ml-auto rounded-[7px] px-3 py-[6px] text-[12px] text-muted-foreground transition-colors hover:text-foreground"
          >
            关闭
          </button>
          {!confirmed && (
            <button
              type="button"
              disabled={busy || !canConfirm(intake)}
              onClick={() => onConfirm(intake)}
              className={cn(BTN_PRIMARY, 'h-[30px]')}
              title={canConfirm(intake) ? '采纳系统建议，绑定到该项目' : '系统未给出可信建议'}
            >
              <Check className="h-3.5 w-3.5" aria-hidden />
              确认绑定
            </button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
