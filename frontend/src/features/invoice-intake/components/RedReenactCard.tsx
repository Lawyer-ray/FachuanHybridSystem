import { useState } from 'react'
import { ArrowDown, Info, RefreshCw, SplitSquareHorizontal } from 'lucide-react'

import { formatAmount, RED_REENACT_COPY, RED_TONE } from '../constants'
import { amountText, canConfirmRedReenact } from '../domain'
import type { InvoiceIntake, RedGroup } from '../types'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { BTN_PRIMARY, ROW_BTN } from '@/components/shared/panel-styles'
import { cn } from '@/lib/utils'

/**
 * 红字发票 · 冲红重开卡（一张卡代替原来的两行）。
 *
 * ## 为什么必须合成一张卡
 *
 * 红票和重开的新蓝票是**两条独立 intake**，但它们是一件事：冲掉原票、换上新票。
 * 分两行摆着，人得自己看出「这两条是同一件事」，还会以为要确认两次。
 *
 * ## 为什么主按钮会禁用
 *
 * 红票金额未识别时**不允许**冲红：冲红要往 `invoiced_amount` 里减一笔负数，金额
 * 不知道就减不了，账直接错。此时只给「重解析」——把那张红票的 PDF 重跑一遍
 * 才是正解，逼用户「先想个金额」等于给坏数据开后门。
 *
 * 原票不在库（`group.original === null`）时整组只能人工处理：没有原票可作废，
 * 冲红动作落不了地。
 */
export function RedReenactCard({
  group,
  red,
  busy,
  onConfirmReenact,
  onConfirmOnly,
  onReparse,
  onDetail,
}: {
  /** 组结构（后端下发）：原票 / 红票 / 新票，是禁用判据的唯一来源 */
  group: RedGroup
  /** 红票那条 intake：金额文案与被禁用原因都从这里取 */
  red: InvoiceIntake
  busy: boolean
  onConfirmReenact: () => void
  onConfirmOnly: () => void
  onReparse: () => void
  onDetail: () => void
}) {
  const [askRedOnly, setAskRedOnly] = useState(false)
  const reenactable = canConfirmRedReenact(group)
  const blocked = group.original == null
  const reissue = group.reissue

  return (
    <div className="rounded-[10px] border border-destructive/30 bg-card px-2.5 py-2">
      {/* 抬头：红票标识 + 项目名 */}
      <div className="flex items-baseline gap-2">
        <span
          className={cn(
            'flex-none rounded-[99px] border px-[7px] py-[1px] text-[10px] font-semibold',
            RED_TONE.chip,
          )}
        >
          {RED_TONE.label}
        </span>
        <span className="truncate text-[11.5px] font-medium" title={red.confirmed_contract_name ?? ''}>
          {red.confirmed_contract_name || red.suggested_contract_name || '项目待定'}
        </span>
      </div>

      {/* 三段：原票 → 红票 → 新票 */}
      <div className="mt-[6px] flex flex-col gap-[2px]">
        <div className="flex items-baseline gap-1.5 text-[11px]">
          <span className="flex-none text-[10.5px] text-muted-foreground">原票</span>
          <span className="truncate font-mono text-[10.5px]">{itemNumber(group.original?.invoice_number)}</span>
          <span className="ml-auto flex-none tabular-nums">{itemAmount(group.original?.total_amount)}</span>
        </div>

        <div className="flex items-center gap-1 pl-1 text-[10.5px] text-destructive">
          <ArrowDown className="h-3 w-3 flex-none" aria-hidden />
          <span>红票</span>
          <span className="truncate font-mono">{itemNumber(group.red.invoice_number)}</span>
          <span className="ml-auto flex-none tabular-nums">{amountText(red)}</span>
        </div>

        <div className="flex items-baseline gap-1.5 text-[11px]">
          <span className="flex-none text-[10.5px] text-muted-foreground">新票</span>
          <span className="truncate font-mono text-[10.5px]">
            {reissue == null ? '未挑到新票' : itemNumber(reissue.invoice_number)}
          </span>
          <span className="ml-auto flex-none tabular-nums">{reissue == null ? '—' : itemAmount(reissue.total_amount)}</span>
        </div>
      </div>

      {/* 后果说明：点下去发生什么，必须先说得清 */}
      <div className="mt-[5px] flex items-start gap-1 text-[10.5px] leading-[1.35] text-muted-foreground">
        <Info className="mt-[1px] h-3 w-3 flex-none opacity-60" aria-hidden />
        <span className="min-w-0">{blocked ? RED_REENACT_COPY.blocked : '冲红后原票作废，新票替代原票入账'}</span>
      </div>

      {/* 动作行 */}
      <div className="mt-[7px] flex items-center gap-1.5">
        <button
          type="button"
          disabled={busy || !reenactable}
          onClick={onConfirmReenact}
          className={cn(BTN_PRIMARY, 'h-[26px] px-2.5 text-[10.5px]')}
          title={reenactTitle(group, reenactable)}
        >
          <SplitSquareHorizontal className="h-3 w-3" aria-hidden />
          {RED_REENACT_COPY.confirm}
        </button>

        <button
          type="button"
          disabled={busy || red.total_amount == null || red.total_amount === ''}
          onClick={() => setAskRedOnly(true)}
          className={ROW_BTN}
          title="只冲红、不重开：原票作废，不再收新票"
        >
          {RED_REENACT_COPY.confirmOnly}
        </button>

        {/* 金额未识别时唯一能做的事是重解析，所以它紧贴主按钮 */}
        {!reenactable && !blocked && red.total_amount == null && (
          <button type="button" disabled={busy} onClick={onReparse} className={ROW_BTN} title="重新解析这张红票的 PDF">
            <RefreshCw className="h-3 w-3" aria-hidden />
            重解析
          </button>
        )}

        <button
          type="button"
          onClick={onDetail}
          className="ml-auto rounded-[6px] px-1 py-[2px] text-[10.5px] text-muted-foreground transition-colors hover:text-foreground"
        >
          详情
        </button>
      </div>

      <ConfirmDialog
        open={askRedOnly}
        onOpenChange={setAskRedOnly}
        title="只冲红、不重开？"
        description="原票将作废且不再收新票。若财务已经把正确的票重开出来了，请改用「冲红并确认重开」。"
        confirmText="确认仅冲红"
        tone="destructive"
        pending={busy}
        onConfirm={() => {
          onConfirmOnly()
          setAskRedOnly(false)
        }}
      />
    </div>
  )
}

/** 票号尾部片段：20 位整串在侧栏放不下，尾 6 位足够人对上 */
function itemNumber(invoiceNumber: string | undefined): string {
  const text = (invoiceNumber ?? '').trim()
  if (text === '') return '未识别'
  return text.length > 6 ? `…${text.slice(-6)}` : text
}

/** 组内金额（非红票段）：识别失败给占位而不是留空 */
function itemAmount(amount: string | null | undefined): string {
  if (amount == null || amount === '') return '金额未识别'
  return formatAmount(amount)
}

/** 主按钮禁用原因要说清「缺哪一条」，而不是只说不能点 */
function reenactTitle(group: RedGroup, reenactable: boolean): string {
  if (reenactable) return '一次完成冲红 + 重开入账'
  if (group.original == null) return RED_REENACT_COPY.blocked
  if (group.red.total_amount == null || group.red.total_amount === '') return '红票金额未识别，请先重解析这张红票'
  return '组内还没有可重开的蓝票，只能「仅冲红」'
}
