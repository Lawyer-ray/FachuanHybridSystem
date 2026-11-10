import { AlertTriangle } from 'lucide-react'

import { amountText } from '../domain'
import type { Intake } from '../types'
import { BTN_PRIMARY } from '@/components/shared/panel-styles'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

/**
 * 确认归属前的二次确认。
 *
 * 这是**财务动作**——点下去就会生成一条收款记录。所以必须把三件事摆清楚：
 * 金额、落到哪个项目、以及（当系统只有金额证据时）明确的核对警告。
 */
export function ConfirmDialog({
  intake,
  contractName,
  open,
  onOpenChange,
  onConfirm,
  busy,
}: {
  intake: Intake | null
  /** 目标项目名（省略时用系统建议的名字）。id 由调用方在 onConfirm 里使用 */
  contractName?: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
  busy: boolean
}) {
  if (!intake) return null
  const target = contractName ?? intake.suggested_contract_name ?? '（未选择）'
  const top = intake.candidates[0]
  const risky = top?.kind === 'amount_only'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[440px]">
        <DialogHeader>
          <DialogTitle className="text-[15px]">确认到账归属</DialogTitle>
          <DialogDescription className="text-[12px]">确认后将立即写入该项目的收款记录。</DialogDescription>
        </DialogHeader>

        <dl className="mt-1 space-y-1.5 rounded-[8px] border border-border bg-secondary/40 px-3 py-2.5 text-[12.5px]">
          <div className="flex gap-2">
            <dt className="w-[64px] flex-none text-muted-foreground">金额</dt>
            <dd className="font-semibold tabular-nums">{amountText(intake)}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-[64px] flex-none text-muted-foreground">付款人</dt>
            <dd className="min-w-0 break-words">{intake.display_payer}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-[64px] flex-none text-muted-foreground">到账日</dt>
            <dd>{intake.received_at}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-[64px] flex-none text-muted-foreground">归属项目</dt>
            <dd className="min-w-0 break-words font-medium">{target}</dd>
          </div>
        </dl>

        {risky && (
          <div className="mt-2 flex items-start gap-1.5 rounded-[8px] border border-status-yellow/40 bg-status-yellow-bg px-2.5 py-2 text-[11.5px] text-status-yellow">
            <AlertTriangle className="mt-[1px] h-3.5 w-3.5 flex-none" aria-hidden />
            <span>系统只找到「金额恰好相等」的项目，没有任何付款人或案号证据。请务必核对后再确认。</span>
          </div>
        )}

        {intake.excluded_hints.length > 0 && (
          <div className="mt-2 rounded-[8px] border border-border px-2.5 py-2 text-[11px] text-muted-foreground">
            {intake.excluded_hints.map((h) => (
              <div key={h.contract_id} className="break-words">
                · {h.contract_name}：{h.note}
              </div>
            ))}
          </div>
        )}

        <DialogFooter className="mt-3 gap-2">
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="rounded-[7px] px-3 py-[6px] text-[12.5px] text-muted-foreground transition-colors hover:text-foreground"
          >
            取消
          </button>
          <button type="button" disabled={busy} onClick={onConfirm} className={BTN_PRIMARY}>
            {busy ? '写入中…' : '确认并写入收款记录'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
