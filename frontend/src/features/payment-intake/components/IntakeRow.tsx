import { AlertTriangle, ArrowRightLeft, Check, Info } from 'lucide-react'

import { KIND_STYLES } from '../constants'
import { amountText, candidateReason, intakeHeadline, intakeShape } from '../domain'
import type { Intake } from '../types'
import { ROW_BTN } from '@/components/shared/panel-styles'
import { cn } from '@/lib/utils'

/**
 * 首页「待认领款项」里的单行。
 *
 * 侧栏很窄，所以只放最关键的四件事：**多少钱、谁付的、建议哪个项目、能不能直接确认**。
 * 被排除的线索（已收齐的项目）单独一行灰字，它常是解开疑问的钥匙
 * （例如"这笔钱为什么匹配不上——因为那个项目已经收满了"）。
 */
export function IntakeRow({
  intake,
  busy,
  onConfirm,
  onChange,
  onDetail,
}: {
  intake: Intake
  busy: boolean
  /** 采纳系统建议直接确认（仅 hasUsableSuggestion 为真时可用） */
  onConfirm: () => void
  /** 打开「换个项目」弹窗 */
  onChange: () => void
  onDetail: () => void
}) {
  const shape = intakeShape(intake)
  const top = intake.candidates[0]
  const style = top ? KIND_STYLES[top.kind] : null
  const headline = intakeHeadline(intake)

  return (
    <div className="rounded-[10px] border border-border bg-card px-2.5 py-2 transition-colors hover:border-zinc-300">
      {/* 第一行：金额 + 日期 + 判定徽标 */}
      <div className="flex items-baseline gap-2">
        <span className="text-[14px] leading-none font-semibold tabular-nums">{amountText(intake)}</span>
        <span className="text-[10.5px] text-muted-foreground">{intake.received_at}</span>
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

      {/* 第二行：付款人（代付时带出代付方） */}
      <div className="mt-[3px] truncate text-[11.5px] text-secondary-foreground">{intake.display_payer}</div>

      {/* 第三行：结论 */}
      <div
        className={cn(
          'mt-[5px] flex items-start gap-1 text-[11.5px] leading-[1.35]',
          shape === 'amountOnly' ? 'text-status-yellow' : shape === 'unmatched' ? 'text-muted-foreground' : 'text-foreground',
        )}
      >
        {shape === 'amountOnly' ? (
          <AlertTriangle className="mt-[1px] h-3 w-3 flex-none" aria-hidden />
        ) : (
          <Info className="mt-[1px] h-3 w-3 flex-none opacity-50" aria-hidden />
        )}
        <span className="min-w-0 break-words">{headline}</span>
      </div>

      {/* 候选理由（有就展示，人靠它判断"系统凭什么是这么想的"） */}
      {top && candidateReason(top) && (
        <div className="mt-[2px] truncate pl-4 text-[10.5px] text-muted-foreground">{candidateReason(top)}</div>
      )}

      {/* 被排除的线索：一句话灰字，常是理解"为什么没匹配上"的关键 */}
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
          disabled={busy || !intake.suggested_contract_id}
          onClick={onConfirm}
          className={cn(ROW_BTN, 'font-semibold')}
          title={
            intake.suggested_contract_id
              ? '采纳系统建议，写入该项目的收款记录'
              : '系统未给出可信建议，请选「换个项目」'
          }
        >
          <Check className="h-3 w-3" aria-hidden />
          确认
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
