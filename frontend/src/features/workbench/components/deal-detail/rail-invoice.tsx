/**
 * 发票按收款分组的行级 UI：分组眉头 + 发票行 + 归属动作按钮。
 *
 * 归属按钮的显示规则（教训：曾只在一笔收款时渲染，结果页面上根本没有入口）：
 * - **未归属**的票：一定给「关联」按钮。只有一笔收款时它直接指向那一笔（不让人选，
 *   但必须能点）；多笔时才出现「关联 ¥X」的分歧。
 * - **已归属**的票：多笔收款时给「改挂」，单笔时没有别的去处不给按钮；
 *   「解除关联」始终保留，这是挂错的出口。
 */

import { FileText, Loader2, Unlink } from 'lucide-react'

import type { PaymentInvoice } from '../../api'
import { CopyInvoiceFileButton } from './PaymentInvoiceZone'

/** 分组眉头：票挂在哪笔收款下面（金额 + 日期），未归属的用一句话说明待处理 */
export function InvoiceGroupHead({
  count,
  amount,
  date,
  unlinked,
}: {
  count: number
  amount: string | null
  date: string | null
  unlinked: boolean
}) {
  if (unlinked) {
    return (
      <div className="mt-1 mb-[3px] flex items-baseline gap-1.5 text-[10.5px]">
        <span className="font-[620] text-status-yellow">未关联收款</span>
        <span className="tabular-nums text-muted-foreground/60">· {count} 张待处理</span>
      </div>
    )
  }
  return (
    <div className="mt-1 mb-[3px] flex items-baseline gap-1.5 text-[10.5px] text-muted-foreground/80">
      <span className="font-[620]">归 · {amount ?? '—'}</span>
      {date && <span className="tabular-nums text-muted-foreground/60">{date}</span>}
      <span className="tabular-nums text-muted-foreground/50">· {count} 张</span>
    </div>
  )
}

/** 发票行：文件名 + 金额 + 归属操作 + 复制文件（微信 ⌘V 直发） */
export function InvoiceRow({
  inv,
  busy,
  payments,
  onLink,
  onUnlink,
}: {
  inv: PaymentInvoice
  busy: boolean
  /** 可选目标收款（金额已格式化，直接进按钮文案/tooltip） */
  payments: Array<{ id: number; amount: string }>
  onLink: (paymentId: number) => void
  onUnlink: () => void
}) {
  const linked = inv.payment_id != null
  /** 未归属：合同下有收款就能挂（单笔直接挂、多笔每笔一个候选）；已归属：仅多笔时可改挂 */
  const linkTargets = linked
    ? payments.length > 1
      ? payments.filter((p) => p.id !== inv.payment_id)
      : []
    : payments

  return (
    <li className="flex items-center gap-1.5 border-b border-border-light py-[5px] text-[11.5px] last:border-b-0">
      <FileText className="size-3 flex-none text-muted-foreground/60" />
      <span className="min-w-0 flex-1 truncate" title={inv.display_filename}>
        {inv.display_filename}
      </span>
      <span className="flex-none whitespace-nowrap text-muted-foreground tabular-nums" title="价税合计">
        {inv.total_amount ? '¥' + inv.total_amount : '—'}
      </span>
      {linkTargets.map((p) => {
        const label = linked ? '改挂' : payments.length > 1 ? `关联 ${p.amount}` : '关联'
        const hint = `${linked ? '改挂' : '关联'}到 ${p.amount} 那笔收款`
        return (
          <button
            key={p.id}
            type="button"
            title={hint}
            aria-label={hint}
            className={
              'flex-none rounded-[5px] px-1.5 py-0.5 text-[10px] font-[620] transition-colors disabled:opacity-50 ' +
              (linked
                ? 'text-muted-foreground/80 hover:bg-secondary hover:text-foreground'
                : 'bg-secondary text-secondary-foreground hover:bg-secondary/70')
            }
            disabled={busy}
            onClick={() => onLink(p.id)}
          >
            {busy ? <Loader2 className="size-3 animate-spin" /> : label}
          </button>
        )
      })}
      {linked && (
        <button
          type="button"
          title="解除关联（发票退回未关联，重新挂到正确的收款）"
          aria-label="解除关联"
          className="flex-none rounded-[5px] p-1 text-muted-foreground/60 transition-colors hover:bg-secondary hover:text-status-red disabled:opacity-50"
          disabled={busy}
          onClick={onUnlink}
        >
          {busy ? <Loader2 className="size-3 animate-spin" /> : <Unlink className="size-3" />}
        </button>
      )}
      <CopyInvoiceFileButton invoiceId={inv.id} filename={inv.display_filename} />
    </li>
  )
}
