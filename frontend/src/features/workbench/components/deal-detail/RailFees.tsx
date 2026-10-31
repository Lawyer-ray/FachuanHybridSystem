import { useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { EmptyBlock } from '@/components/shared/AsyncState'
import { errMessage } from '@/lib/errors'
import { fmtCNDate, fmtMoney } from '../../domain'
import {
  attachPaymentInvoice,
  contractInvoiceKeys,
  detachPaymentInvoice,
  listContractInvoices,
  uploadContractInvoices,
  type PaymentInvoice,
} from '../../api'
import type { WorkbenchDeal } from '../../types'
import { feeStats } from './detail-domain'
import { groupsForReview } from './invoice-auto-link'
import { InvoiceGroupHead, InvoiceRow } from './rail-invoice'
import { InvoiceStatusBadge, StatCell, Subhead } from './rail-ui'
import { KV, RailAction } from './ui'

/**
 * 统一的「收费」节：钱与票两条线**分开**呈现——收款是钱到账的事实（金额/日期/
 * 开票状态），发票是票本身（识别归档后的文件，可复制直发客户）。两种顺序都顺：
 * 先收款后开票 → ＋记收款（弹窗里拖票归属到这笔收款）；先开票后收款 → ＋传发票
 * 或把票直接拖进本节（先挂合同名下，收款后关联到那笔收款）。
 *
 * 发票按**收款分组**显示（见 groupsForReview）：票挂在哪笔钱下面一目了然，
 * 每行可「关联/改挂」或「解除关联」——挂错不需要重传。未归属的那一组单独放
 * 最后、整组只提示一次（不再逐行重复黄标签）。
 *
 * 整节是拖放目标：拖票悬停时高亮提示落点（传到合同名下）。
 */
export function RailFees({
  deal,
  moneyRows,
  onAddPayment,
  onOpenInvoices,
  onChanged,
}: {
  deal: WorkbenchDeal
  moneyRows: Array<[string, string]>
  onAddPayment: () => void
  onOpenInvoices: () => void
  /**
   * 发票归属/上传成功后通知页面刷新合同。
   *
   * 必须回调给页面而不是只 invalidate 本节的发票缓存：开票金额与「已开票」
   * 统计格来自**合同**数据（deal.totalInvoiced / payment.invoice_status），
   * 只刷发票列表的话金额会原地不动，看起来像「关联没生效」——
   * 律师已经因为要手动刷新页面提过一次意见。
   */
  onChanged: () => void
}) {
  const stats = feeStats(deal)
  const qc = useQueryClient()
  const invoicesQ = useQuery({
    queryKey: contractInvoiceKeys.all(deal.id),
    queryFn: () => listContractInvoices(deal.id),
    staleTime: 30_000,
  })
  const invoices = useMemo(() => invoicesQ.data ?? [], [invoicesQ.data])
  /** 收款行（带 id）才算归属目标：ContractPaymentOut.id 是可空的 */
  const payTargets = useMemo(
    () =>
      deal.payments
        .filter((p): p is typeof p & { id: number } => p.id != null)
        .map((p) => ({ id: p.id, amount: fmtMoney(p.amount) ?? '' })),
    [deal.payments],
  )
  const groups = useMemo(() => groupsForReview(invoices, payTargets), [invoices, payTargets])
  const unlinkedCount = invoices.filter((inv) => inv.payment_id == null).length
  /** 关联/解除关联中的发票 id（行内图标转圈用，同时防重复点击） */
  const [busyId, setBusyId] = useState<number | null>(null)

  const [dragDepth, setDragDepth] = useState(0)
  const [uploading, setUploading] = useState(false)
  const dragging = dragDepth > 0
  const fileRef = useRef<HTMLInputElement | null>(null)

  /** 发票缓存 + 合同（开票金额/统计格/收款徽标）一起刷，缺一个就出现「半新半旧」 */
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: contractInvoiceKeys.all(deal.id) })
    onChanged()
  }

  /** 拖发票到本节：直接传到合同名下（先开票后付款的最短路径） */
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragDepth(0)
    const files = Array.from(e.dataTransfer.files)
    if (files.length) void uploadInvoices(files)
  }

  const uploadInvoices = async (files: File[]) => {
    if (uploading) return
    setUploading(true)
    try {
      const result = await uploadContractInvoices(deal.id, files)
      if (result.failed.length) {
        toast.error(result.failed.map((f) => `${f.filename}：${f.reason}`).join('；'))
      }
      if (result.saved.length) {
        toast.success(`已识别归档 ${result.saved.length} 张发票`)
        refresh()
      }
    } catch (e) {
      toast.error(errMessage(e, '发票上传失败，请重试'))
    } finally {
      setUploading(false)
    }
  }

  /**
   * 关联/改挂到目标收款。后端要求「未关联」才能 attach，所以已关联的票先 detach
   * 再 attach——两步都在这里，用户只看到一次点击、一次结果提示。
   */
  const relink = async (inv: PaymentInvoice, paymentId: number) => {
    if (busyId != null) return
    setBusyId(inv.id)
    try {
      if (inv.payment_id != null) await detachPaymentInvoice(inv.id)
      await attachPaymentInvoice(inv.id, paymentId)
      toast.success(inv.payment_id == null ? '已关联到这笔收款' : '已改挂到这笔收款')
      refresh()
    } catch (e) {
      toast.error(errMessage(e, '关联失败，请重试'))
      refresh()
    } finally {
      setBusyId(null)
    }
  }

  /** 解除关联：票退回合同名下，后端同步重算原收款的开票金额 */
  const unlink = async (inv: PaymentInvoice) => {
    if (busyId != null) return
    setBusyId(inv.id)
    try {
      await detachPaymentInvoice(inv.id)
      toast.success('已解除关联，发票回到未关联收款')
      refresh()
    } catch (e) {
      toast.error(errMessage(e, '解除关联失败，请重试'))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div
      onDragEnter={(e) => {
        if (!e.dataTransfer.types.includes('Files')) return
        e.preventDefault()
        setDragDepth((d) => d + 1)
      }}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes('Files')) e.preventDefault()
      }}
      onDragLeave={() => setDragDepth((d) => Math.max(0, d - 1))}
      onDrop={onDrop}
      className={
        'relative border-t border-border-light px-[18px] pt-3.5 pb-[15px] first:border-t-0 first:pt-[15px] transition-colors ' +
        (dragging ? 'rounded-[10px] border border-dashed border-foreground/60 bg-secondary/70' : '')
      }
    >
      {dragging && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center text-[12px] font-[620] text-secondary-foreground">
          松手上传发票（自动识别、归档到发票文件夹并重命名）
        </div>
      )}

      {/* 节头：收费事实的入口双动作——先记钱（记收款）或先记票（传发票） */}
      <div className="mb-[9px] flex items-center gap-2">
        <h4 className="text-[11px] font-[650] tracking-[0.07em] text-muted-foreground/80">收费</h4>
        {(uploading || invoicesQ.isFetching) && <Loader2 className="size-3 animate-spin text-muted-foreground" />}
        <span className="ml-auto flex gap-3">
          <RailAction onClick={onAddPayment}>＋ 记收款</RailAction>
          <RailAction onClick={onOpenInvoices}>＋ 传发票</RailAction>
        </span>
      </div>

      {moneyRows.length > 0 && (
        <div className="mb-2">
          {moneyRows.map(([k, v]) => (
            <KV key={k} k={k} v={v} kw={56} />
          ))}
        </div>
      )}

      {/* 三格统计：钱到没到、票开没开，一眼分清（0 也是事实，显式给出） */}
      <div className="grid grid-cols-3 divide-x divide-border-light rounded-[10px] border border-border-light bg-secondary/30">
        <StatCell label="已收" value={stats.received} />
        <StatCell label="已开票" value={stats.invoiced} />
        <StatCell label="未收" value={stats.unpaid ?? '—'} muted={stats.unpaid == null} />
      </div>

      {/* 收款：逐笔的钱（开票状态跟钱走，票归属到收款） */}
      <Subhead title="收款" count={deal.payments.length + deal.payRecords.length} />
      {deal.payments.length + deal.payRecords.length === 0 ? (
        <EmptyBlock className="justify-start px-0 py-1 text-left text-xs text-muted-foreground/70">
          还没有收款记录
        </EmptyBlock>
      ) : (
        <>
          {deal.payments.map((p) => (
            <div key={'pay' + p.id} className="border-b border-border-light py-[6px] last:border-b-0">
              <div className="flex items-baseline gap-2 text-[13px]">
                <b className="font-[680] tabular-nums">{fmtMoney(p.amount) ?? '¥0'}</b>
                <InvoiceStatusBadge status={p.invoice_status} label={p.invoice_status_label} />
                <span className="ml-auto text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">
                  {fmtCNDate(p.received_at)}
                </span>
              </div>
              {p.note && <div className="mt-px text-[11px] leading-[1.5] text-muted-foreground">{p.note}</div>}
            </div>
          ))}
          {deal.payRecords.map((p, i) => (
            <div key={'rec' + (p.id ?? i)} className="border-b border-border-light py-[6px] last:border-b-0">
              <div className="flex items-baseline gap-2 text-[13px]">
                <b className="font-[680] tabular-nums">{fmtMoney(p.amount) ?? '¥0'}</b>
                <span className="rounded-[5px] bg-secondary px-1.5 py-px text-[10px] font-[620] text-muted-foreground">客户付款记录</span>
                <span className="ml-auto text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">
                  {fmtCNDate(p.created_at)}
                </span>
              </div>
              {p.note && <div className="mt-px text-[11px] leading-[1.5] text-muted-foreground">{p.note}</div>}
            </div>
          ))}
        </>
      )}

      {/* 发票：票的档案（重命名后的文件可一键复制直发微信），按收款分组、行内可改挂 */}
      <Subhead title="发票" count={invoices.length} />
      {invoices.length === 0 ? (
        <button
          type="button"
          className="w-full rounded-[8px] border border-dashed border-border py-2 text-[11.5px] text-muted-foreground/80 transition-colors hover:border-ring/50 hover:bg-secondary/40"
          onClick={() => fileRef.current?.click()}
        >
          拖入或点击上传发票（自动识别、归档、重命名）
        </button>
      ) : (
        <div className="flex flex-col">
          {groups.map((group) => {
            const target = group.paymentId == null ? null : deal.payments.find((p) => p.id === group.paymentId)
            return (
              <div key={group.paymentId ?? 'unlinked'} className="mb-1.5 last:mb-0">
                <InvoiceGroupHead
                  count={group.invoices.length}
                  amount={target ? fmtMoney(target.amount) : null}
                  date={target ? fmtCNDate(target.received_at) : null}
                  unlinked={group.paymentId == null}
                />
                <ul className="flex flex-col">
                  {group.invoices.map((inv) => (
                    <InvoiceRow
                      key={inv.id}
                      inv={inv}
                      busy={busyId === inv.id}
                      payments={payTargets}
                      onLink={(paymentId) => void relink(inv, paymentId)}
                      onUnlink={() => void unlink(inv)}
                    />
                  ))}
                </ul>
              </div>
            )
          })}
          {unlinkedCount > 0 && (
            <p className="mt-1 text-[10.5px] leading-[1.5] text-muted-foreground/70">
              「未关联收款」的票不属于任何一笔到账钱，记账上还没算进「已开票」。点行内「关联」挂到对应收款即可。
            </p>
          )}
        </div>
      )}
      <input
        ref={fileRef}
        type="file"
        multiple
        accept=".pdf,.jpg,.jpeg,.png"
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          e.target.value = ''
          if (files.length) void uploadInvoices(files)
        }}
      />
    </div>
  )
}
