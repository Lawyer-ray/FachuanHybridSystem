import { ArrowRightLeft, Check, Info } from 'lucide-react'

import { MATCH_KIND_STYLES, PAYMENT_PICK_LABELS } from '../constants'
import { amountText, canConfirm, invoiceHeadline } from '../domain'
import type { InvoiceIntake } from '../types'
import { ROW_BTN } from '@/components/shared/panel-styles'
import { cn } from '@/lib/utils'

/**
 * 首页「待认领发票」里的单行。
 *
 * 侧栏很窄，所以只放最关键的四件事：**多少钱、谁买的、建议哪个项目、能不能确认**。
 * 与 `payment-intake/components/IntakeRow.tsx` 同一套视觉语言（同字号层级、
 * 同 ROW_BTN、同卡内卡边框），但数据语义不同，故各自独立实现而非共用组件。
 *
 * 被排除的线索（已结案/已归档的项目）单独一行灰底小字：它常是解开疑问的钥匙
 * （例如「为什么这张票匹配不上——那个项目已经结案了」）。
 */
export function InvoiceIntakeRow({
  intake,
  busy,
  onConfirm,
  onChange,
  onDetail,
}: {
  intake: InvoiceIntake
  busy: boolean
  /** 采纳系统建议直接绑定（仅 canConfirm 为真时可用） */
  onConfirm: () => void
  /** 打开「换个项目」弹窗 */
  onChange: () => void
  onDetail: () => void
}) {
  // 徽标表达「系统最看重哪一条信号」，取候选里最高等级的那档
  const kind = intake.candidates.find((c) => c.kind === 'project_code')?.kind ?? intake.candidates[0]?.kind
  const style = kind ? MATCH_KIND_STYLES[kind] : null
  const headline = invoiceHeadline(intake)
  const hasSuggestion = intake.suggested_contract_id != null
  const confidence = intake.payment_pick_confidence

  return (
    <div className="rounded-[10px] border border-border bg-card px-2.5 py-2 transition-colors hover:border-zinc-300">
      {/* 第一行：金额 + 开票日期 + 匹配信号徽标 */}
      <div className="flex items-baseline gap-2">
        <span className="text-[14px] leading-none font-semibold tabular-nums">{amountText(intake)}</span>
        <span className="text-[10.5px] text-muted-foreground">{intake.invoice_date ?? '日期未识别'}</span>
        {style && (
          <span
            className={cn(
              'ml-auto flex-none rounded-[99px] border px-[7px] py-[1px] text-[10px] font-semibold',
              style.chip,
            )}
          >
            {style.label}
          </span>
        )}
      </div>

      {/* 第二行：购买方（后端已脱敏，去掉了「（个人）」） */}
      <div className="mt-[3px] truncate text-[11.5px] text-secondary-foreground">{intake.buyer_name || '购买方未识别'}</div>

      {/* 第三行：结论 */}
      <div
        className={cn(
          'mt-[5px] flex items-start gap-1 text-[11.5px] leading-[1.35]',
          hasSuggestion ? 'text-foreground' : 'text-muted-foreground',
        )}
      >
        {hasSuggestion ? (
          <Check className="mt-[1px] h-3 w-3 flex-none text-status-green" aria-hidden />
        ) : (
          <Info className="mt-[1px] h-3 w-3 flex-none opacity-50" aria-hidden />
        )}
        <span className="min-w-0 break-words">{headline}</span>
      </div>

      {/* 预选收款的确定性：金额不符是最需要提示的一档，单独染黄 */}
      {confidence && (
        <div
          className={cn(
            'mt-[2px] truncate pl-4 text-[10.5px]',
            confidence === 'amount_mismatch' ? 'text-status-yellow' : 'text-muted-foreground',
          )}
        >
          {PAYMENT_PICK_LABELS[confidence]}
          {intake.payment_pick_note && confidence !== 'exact' ? `（${intake.payment_pick_note}）` : ''}
        </div>
      )}

      {/* 被排除的线索：一句话灰字，常是理解「为什么没匹配上」的关键 */}
      {intake.excluded_hints.length > 0 && (
        <div className="mt-[4px] rounded-[6px] bg-secondary/60 px-1.5 py-[3px] text-[10.5px] text-muted-foreground">
          {intake.excluded_hints.map((h) => (
            <div key={h.contract_id} className="truncate" title={`${h.contract_name}｜${h.note}`}>
              ⓘ {h.contract_name}：{h.note}
            </div>
          ))}
        </div>
      )}

      {/* 动作行 */}
      <div className="mt-[7px] flex items-center gap-1.5">
        <button
          type="button"
          disabled={busy || !canConfirm(intake)}
          onClick={onConfirm}
          className={cn(ROW_BTN, 'font-semibold')}
          title={hasSuggestion ? '采纳系统建议，绑定到该项目' : '系统未给出可信建议，请选「换个项目」'}
        >
          <Check className="h-3 w-3" aria-hidden />
          确认绑定
        </button>
        <button type="button" disabled={busy} onClick={onChange} className={ROW_BTN}>
          <ArrowRightLeft className="h-3 w-3" aria-hidden />
          换个项目
        </button>
        <button
          type="button"
          onClick={onDetail}
          className="ml-auto rounded-[6px] px-1 py-[2px] text-[10.5px] text-muted-foreground transition-colors hover:text-foreground"
        >
          详情
        </button>
      </div>
    </div>
  )
}
