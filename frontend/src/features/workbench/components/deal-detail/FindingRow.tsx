import { AlertTriangle, Check, Loader2, X } from 'lucide-react'

import { cn } from '@/lib/utils'

import {
  CONSEQUENCE_LABEL,
  DELIVERY_LABEL,
  REJECT_REASON_LABEL,
  RISK_SOURCE_LABEL,
  RULE_CLASS_LABEL,
  SOURCE_WEIGHT_LABEL,
  STATUS_LABEL,
  labelOf,
  type FindingItem,
  type FindingStatus,
} from './doc-review-api'

/** 状态配色：终态一律弱化 + 删除线（律师一眼看出这条已经处理过） */
const STATUS_TONE: Record<FindingStatus, string> = {
  proposed: 'text-muted-foreground',
  accepted: 'text-status-green',
  rejected: 'text-muted-foreground line-through',
  stale: 'text-status-yellow',
  moot: 'text-muted-foreground line-through',
  merged: 'text-muted-foreground line-through',
  unanchored: 'text-status-yellow',
}

/**
 * 清单里的一行结论。
 *
 * **从 `ReviewPanel` 抽出来**：面板本身要管轮询、批量决策、两个确认弹窗，
 * 已经 450 行（eslint `max-lines` 上限）；单行卡片的展示规则又是最容易被改来
 * 改去的一块，独立出来更好改也更好测。
 *
 * 四条展示纪律：
 * - 「锚点失效」必须显眼：律师点了会发现画布跳不到，不如提前说清；
 * - 驳回理由码要回显：让律师知道这条为什么被标成「驳回：商业让步」；
 * - 交付载体要标（修订/批注/仅清单）：决定他点「采纳」之后文件里会出现什么；
 * - 强制性违规标红角标：它可能导致条款无效，不能被当成普通建议；
 * - 结论要能溯源（「据：法律规定」），辅助来源弱化显示。
 */
export function FindingRow({
  finding,
  busy,
  active,
  onLocate,
  onAccept,
  onReject,
  onMoot,
}: {
  finding: FindingItem
  busy: boolean
  active: boolean
  onLocate: () => void
  onAccept: () => void
  onReject: () => void
  onMoot: () => void
}) {
  const decided = finding.status !== 'proposed'
  const stale = finding.status === 'stale' || finding.status === 'unanchored'
  const riskSource = labelOf(RISK_SOURCE_LABEL, finding.risk_source)
  const supporting = finding.source_weight === 'supporting'

  return (
    <div
      className={cn(
        'mb-1.5 rounded-[8px] border px-2 py-1.5 transition-colors',
        active ? 'border-primary/50 bg-primary/5' : 'border-border bg-background',
      )}
    >
      <button type="button" onClick={onLocate} className="block w-full text-left" title="在画布中定位">
        <div className="flex items-start gap-1.5">
          <p className="min-w-0 flex-1 text-[12px] font-[600] leading-snug">{finding.title}</p>
          <span className={cn('flex-none text-[10px]', STATUS_TONE[finding.status])}>
            {STATUS_LABEL[finding.status]}
          </span>
        </div>
        <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
          {finding.reason || finding.suggestion_note}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-1">
          {finding.case_ref && (
            <span
              className="rounded-[5px] bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground"
              title={`类案：${finding.case_ref}`}
            >
              案号 {finding.case_ref}
            </span>
          )}
          {finding.rule_class === 'mandatory' && (
            <span className="rounded-[5px] border border-status-red/25 bg-status-red/10 px-1.5 py-0.5 text-[10px] font-semibold text-status-red">
              {RULE_CLASS_LABEL.mandatory}
              {finding.consequence && finding.consequence !== 'breach'
                ? `·${labelOf(CONSEQUENCE_LABEL, finding.consequence)}`
                : ''}
            </span>
          )}
          <span className="rounded-[5px] bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
            {DELIVERY_LABEL[finding.delivery]}
          </span>
          {finding.clause_type && (
            <span className="rounded-[5px] bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {finding.clause_type}
            </span>
          )}
          {riskSource && (
            <span
              className={cn(
                'rounded-[5px] px-1.5 py-0.5 text-[10px]',
                supporting ? 'text-muted-foreground/60' : 'bg-secondary text-muted-foreground',
              )}
              title={finding.source_weight ? labelOf(SOURCE_WEIGHT_LABEL, finding.source_weight) : undefined}
            >
              据：{riskSource}
              {supporting ? '（辅）' : ''}
            </span>
          )}
          {stale && (
            <span className="inline-flex items-center gap-0.5 rounded-[5px] bg-status-yellow/15 px-1.5 py-0.5 text-[10px] text-status-yellow">
              <AlertTriangle className="size-2.5" /> 原文已变
            </span>
          )}
          {finding.reject_reason_code && (
            <span className="rounded-[5px] bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
              驳回：{REJECT_REASON_LABEL[finding.reject_reason_code] ?? finding.reject_reason_code}
            </span>
          )}
        </div>
      </button>

      {!decided && (
        <div className="mt-1.5 flex items-center gap-1">
          <button
            type="button"
            onClick={onAccept}
            disabled={busy}
            className="inline-flex h-[24px] items-center gap-0.5 rounded-[6px] bg-foreground px-1.5 text-[11px] font-semibold text-background disabled:opacity-50"
          >
            {busy ? <Loader2 className="size-3 animate-spin" /> : <Check className="size-3" />}
            采纳
          </button>
          <button
            type="button"
            onClick={onReject}
            disabled={busy}
            className="inline-flex h-[24px] items-center gap-0.5 rounded-[6px] border border-border px-1.5 text-[11px] disabled:opacity-50"
          >
            <X className="size-3" />
            驳回
          </button>
          <button
            type="button"
            onClick={onMoot}
            disabled={busy}
            className="inline-flex h-[24px] items-center rounded-[6px] px-1.5 text-[11px] text-muted-foreground disabled:opacity-50"
            title="我自己已经改过这段了"
          >
            已处理
          </button>
        </div>
      )}
    </div>
  )
}
