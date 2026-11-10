import { useState } from 'react'
import { ArrowRightLeft, Check, Copy, Info, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { copyInvoiceToClipboard } from '../api'
import { MATCH_KIND_STYLES, PAYMENT_PICK_LABELS } from '../constants'
import { amountText, canConfirm, invoiceHeadline } from '../domain'
import type { InvoiceIntake } from '../types'
import { ROW_BTN } from '@/components/shared/panel-styles'
import { errMessage } from '@/lib/errors'
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
/**
 * 复制重命名后的发票文件本体（Finder ⌘C 语义，微信里 ⌘V 直接粘出发票）。
 *
 * 为什么不复用项目详情页那个同名组件：它在 `features/workbench` 内部，
 * 跨 feature import 是硬禁止的（见 frontend/index.md「归属与提权硬规则」）。
 * 逻辑很短，各域一份比破例耦合更划算。
 */
function CopyInvoiceButton({ invoiceId, filename }: { invoiceId: number; filename: string }) {
  const [busy, setBusy] = useState(false)
  const onClick = async () => {
    if (busy) return
    setBusy(true)
    // busy 必须在 finally 里复位：成功分支 return 也要清，否则图标一直转圈
    try {
      const res = await copyInvoiceToClipboard(invoiceId)
      if (res.success && res.copied > 0) {
        toast.success('发票已复制，微信对话框直接 ⌘V 粘贴发送')
        return
      }
      const reason = res.reason === 'unsupported' ? '当前环境不支持复制文件本体' : res.reason || '复制文件本体失败'
      if (await copyText(filename)) toast.info(`${reason}，已复制文件名`)
      else toast.error('复制失败，请改用下载')
    } catch (e) {
      if (await copyText(filename)) toast.error(`${errMessage(e, '复制文件本体失败')}，已复制文件名`)
      else toast.error(errMessage(e, '复制失败，请改用下载'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <button
      type="button"
      disabled={busy}
      onClick={() => void onClick()}
      className={ROW_BTN}
      title={`复制文件（${filename}）`}
    >
      {busy ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
      复制发票
    </button>
  )
}

/** 落板失败时兜底复制文件名（至少能对上文件）。与项目详情页同实现。 */
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

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
  const rows = intake.candidates ?? []
  const kind = rows.find((c) => c.kind === 'project_code')?.kind ?? rows[0]?.kind
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
      {(intake.excluded_hints ?? []).length > 0 && (
        <div className="mt-[4px] rounded-[6px] bg-secondary/60 px-1.5 py-[3px] text-[10.5px] text-muted-foreground">
          {(intake.excluded_hints ?? []).map((h) => (
            <div key={h.contract_id} className="truncate" title={`${h.contract_name}｜${h.note}`}>
              ⓘ {h.contract_name}：{h.note}
            </div>
          ))}
        </div>
      )}

      {/* 已确认：直接给「重命名后的文件名 + 复制」，这是确认完最想做的下一件事 */}
      {intake.status === 'confirmed' && intake.invoice_id ? (
        <>
          <div
            className="mt-[5px] truncate rounded-[6px] bg-secondary/60 px-1.5 py-[3px] text-[10.5px] text-muted-foreground"
            title={intake.invoice_display_filename}
          >
            📄 {intake.invoice_display_filename || '发票已生成'}
          </div>
          <div className="mt-[7px] flex items-center gap-1.5">
            <CopyInvoiceButton invoiceId={intake.invoice_id} filename={intake.invoice_display_filename} />
            <button
              type="button"
              onClick={onDetail}
              className="ml-auto rounded-[6px] px-1 py-[2px] text-[10.5px] text-muted-foreground transition-colors hover:text-foreground"
            >
              详情
            </button>
          </div>
        </>
      ) : (
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
      )}
    </div>
  )
}
