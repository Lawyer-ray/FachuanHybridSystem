import { AlertTriangle, Check, Info } from 'lucide-react'

import { formatAmount, PAYMENT_PICK_LABELS } from '../constants'
import type { InvoiceIntake } from '../types'
import { cn } from '@/lib/utils'

/**
 * 详情里的「收款对照」块 —— 整个详情里**唯一有决策价值**的一段。
 *
 * 律师确认前真正要核的就是这件事：这张票的金额，跟那笔到账对得上吗？
 * 所以这里不只是并排摆两个数字，而是直接给出判定：
 *
 * - 相等 → 绿勾「金额吻合，可放心确认」
 * - 不等 → 黄警示 + **差额**（只说"不相等"没有信息量，说"差 ¥400"才知道该不该管）
 * - 无收款 → 说明这是「先开票后付款」，确认后挂合同名下
 */

/** 金额串 → number（容忍千分位、¥、空格；识别不出返 null） */
function amountOf(raw: string | null | undefined): number | null {
  if (raw == null) return null
  const cleaned = String(raw).replace(/[¥￥,\s，]/g, '')
  if (!cleaned) return null
  const n = Number(cleaned)
  return Number.isFinite(n) ? n : null
}

export function PaymentCompare({ intake }: { intake: InvoiceIntake }) {
  const options = intake.payment_options
  const picked = options.find((o) => o.id === intake.suggested_payment_id) ?? null
  const invoiceAmount = amountOf(intake.total_amount)
  const confidence = intake.payment_pick_confidence

  // 已确认：直接说结果，不再做"建议"判断
  if (intake.status === 'confirmed') {
    const target = intake.confirmed_payment_id
    return (
      <Section title="收款对照">
        <div className="flex items-center gap-1.5 text-[12px] text-status-green">
          <Check className="h-3.5 w-3.5 flex-none" aria-hidden />
          {target ? `已挂到收款 #${target}` : '已挂到项目名下（未指定收款）'}
        </div>
      </Section>
    )
  }

  if (!picked) {
    return (
      <Section title="收款对照">
        <div className="flex items-start gap-1.5 text-[12px] text-muted-foreground">
          <Info className="mt-[2px] h-3.5 w-3.5 flex-none opacity-60" aria-hidden />
          <span>
            {confidence === 'ambiguous'
              ? `该项目有 ${options.length} 笔收款，系统不替你猜是哪一笔；确认时可直接挂到项目名下，或稍后在项目页关联。`
              : '该项目暂无收款记录——属于「先开票后付款」，确认后先挂在项目名下，钱到账后再关联。'}
          </span>
        </div>
      </Section>
    )
  }

  const paidAmount = amountOf(picked.amount)
  const same =
    invoiceAmount != null && paidAmount != null && Math.abs(invoiceAmount - paidAmount) < 0.005
  const diff = invoiceAmount != null && paidAmount != null ? invoiceAmount - paidAmount : null

  return (
    <Section title="收款对照">
      <div className="flex items-center gap-2">
        <span className="text-[13px] font-semibold tabular-nums">
          {intake.total_amount ? formatAmount(intake.total_amount) : '金额未识别'}
        </span>
        <span className="text-[11px] text-muted-foreground">发票</span>
        <span className="text-[11px] text-muted-foreground">↔</span>
        <span className="text-[13px] font-semibold tabular-nums">{formatAmount(picked.amount)}</span>
        <span className="text-[11px] text-muted-foreground">收款 #{picked.id}</span>

        <span
          className={cn(
            'ml-auto flex-none rounded-[99px] border px-[7px] py-[1px] text-[10px] font-semibold',
            same
              ? 'border-status-green/30 bg-status-green-bg text-status-green'
              : 'border-status-yellow/30 bg-status-yellow-bg text-status-yellow',
          )}
        >
          {same ? '金额吻合' : '金额不符'}
        </span>
      </div>

      <div className="mt-[4px] text-[11px] text-muted-foreground">
        到账 {picked.received_at}
        {picked.note ? ` · ${picked.note}` : ''}
      </div>

      {!same && (
        <div className="mt-[5px] flex items-start gap-1 text-[11.5px] leading-[1.4] text-status-yellow">
          <AlertTriangle className="mt-[2px] h-3 w-3 flex-none" aria-hidden />
          <span>
            {diff != null && diff > 0
              ? `发票比收款多 ¥${Math.abs(diff).toFixed(2)}。确认后仍会挂到这笔收款，开票金额按收款上限封顶，差额需另开发票或另建收款。`
              : diff != null
                ? `发票比收款少 ¥${Math.abs(diff).toFixed(2)}。可能是部分开票，确认后该收款会显示「部分开票」。`
                : '发票或收款金额有一方未能识别，建议先核对原件。'}
          </span>
        </div>
      )}

      {confidence && confidence !== 'exact' && (
        <div className="mt-[3px] text-[10.5px] text-muted-foreground">{PAYMENT_PICK_LABELS[confidence]}</div>
      )}
    </Section>
  )
}

/** 详情里的分区块（统一标题 + 分隔线，避免每段各写一遍样式） */
export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-border/70 px-5 py-3 first:border-t-0">
      <div className="mb-[6px] text-[10.5px] font-[650] tracking-[.02em] text-muted-foreground">{title}</div>
      {children}
    </section>
  )
}
