import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { EmptyBlock } from '@/components/shared/AsyncState'
import { errMessage } from '@/lib/errors'
import { fmtCNDate, fmtMoney } from '../../domain'
import {
  contractInvoiceKeys,
  listContractInvoices,
  uploadContractInvoices,
  type PaymentInvoice,
} from '../../api'
import type { WorkbenchDeal } from '../../types'
import { feeStats } from './detail-domain'
import { CopyInvoiceFileButton } from './PaymentInvoiceZone'
import { KV, RailAction } from './ui'

/**
 * 统一的「收费」节：钱与票两条线**分开**呈现——收款是钱到账的事实（金额/日期/
 * 开票状态），发票是票本身（识别归档后的文件，可复制直发客户）。两种顺序都顺：
 * 先收款后开票 → ＋记收款（弹窗里拖票关联到这笔收款）；先开票后收款 → ＋传发票 或把票
 * 直接拖进本节（先挂合同名下，收款后一键关联到那笔收款）。
 *
 * 整节是拖放目标：拖票悬停时高亮提示落点（传到合同名下）。
 */
export function RailFees({
  deal,
  moneyRows,
  onAddPayment,
  onOpenInvoices,
}: {
  deal: WorkbenchDeal
  moneyRows: Array<[string, string]>
  onAddPayment: () => void
  onOpenInvoices: () => void
}) {
  const stats = feeStats(deal)
  const qc = useQueryClient()
  const invoicesQ = useQuery({
    queryKey: contractInvoiceKeys.all(deal.id),
    queryFn: () => listContractInvoices(deal.id),
    staleTime: 30_000,
  })
  const invoices = invoicesQ.data ?? []
  const unlinkedCount = invoices.filter((inv) => inv.payment_id == null).length

  const [dragDepth, setDragDepth] = useState(0)
  const [uploading, setUploading] = useState(false)
  const dragging = dragDepth > 0
  const fileRef = useRef<HTMLInputElement | null>(null)

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
        void qc.invalidateQueries({ queryKey: contractInvoiceKeys.all(deal.id) })
      }
    } catch (e) {
      toast.error(errMessage(e, '发票上传失败，请重试'))
    } finally {
      setUploading(false)
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

      {/* 发票：票的档案（重命名后的文件可一键复制直发微信） */}
      <Subhead
        title="发票"
        count={invoices.length}
        extra={unlinkedCount > 0 ? `未关联收款 ${unlinkedCount} 张` : undefined}
      />
      {invoices.length === 0 ? (
        <button
          type="button"
          className="w-full rounded-[8px] border border-dashed border-border py-2 text-[11.5px] text-muted-foreground/80 transition-colors hover:border-ring/50 hover:bg-secondary/40"
          onClick={() => fileRef.current?.click()}
        >
          拖入或点击上传发票（自动识别、归档、重命名）
        </button>
      ) : (
        <ul className="flex flex-col">
          {invoices.map((inv) => (
            <InvoiceRow key={inv.id} inv={inv} />
          ))}
        </ul>
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

/** 统计格：灰标签 + 粗体金额；未收不可知（风险代理）时降为一字占位 */
function StatCell({ label, value, muted = false }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="flex flex-col items-center gap-px py-[7px]">
      <span className="text-[10.5px] text-muted-foreground/80">{label}</span>
      <b className={'text-[13.5px] font-[680] tabular-nums ' + (muted ? 'text-muted-foreground/50' : 'text-secondary-foreground')}>
        {value}
      </b>
    </div>
  )
}

/** 小节标题（收款/发票两条线各自的眉头）：标题 + 计数 + 右侧补充（未关联收款） */
function Subhead({ title, count, extra }: { title: string; count: number; extra?: string }) {
  return (
    <div className="mt-[13px] mb-[5px] flex items-baseline gap-1.5">
      <span className="text-[11px] font-[650] text-muted-foreground/80">{title}</span>
      <span className="text-[10.5px] tabular-nums text-muted-foreground/60">· {count}</span>
      {extra && <span className="ml-auto text-[10.5px] font-[620] text-status-yellow">{extra}</span>}
    </div>
  )
}

/** 开票状态徽标：跟「这笔钱开没开票」走（票归属到收款，状态随之重算） */
function InvoiceStatusBadge({ status, label }: { status: string; label?: string }) {
  const tone =
    status === 'INVOICED_FULL'
      ? 'bg-status-green/12 text-status-green'
      : status === 'INVOICED_PARTIAL'
        ? 'bg-status-yellow/12 text-status-yellow'
        : 'bg-secondary text-muted-foreground'
  return (
    <span className={'rounded-[5px] px-1.5 py-px text-[10px] font-[620] whitespace-nowrap ' + tone}>
      {label || '未开票'}
    </span>
  )
}

/** 发票行：重命名后的文件名（hover 全名，日期已含在文件名里）+ 金额 + 复制文件（微信 ⌘V 直发） */
function InvoiceRow({ inv }: { inv: PaymentInvoice }) {
  return (
    <li className="flex items-center gap-1.5 border-b border-border-light py-[5px] text-[11.5px] last:border-b-0">
      <FileText className="size-3 flex-none text-muted-foreground/60" />
      <span className="min-w-0 flex-1 truncate" title={inv.display_filename}>
        {inv.display_filename}
      </span>
      {inv.payment_id == null && (
        <span className="flex-none rounded-[5px] bg-status-yellow/12 px-1.5 py-px text-[10px] font-[620] text-status-yellow">
          未关联收款
        </span>
      )}
      <span className="flex-none whitespace-nowrap text-muted-foreground tabular-nums" title="价税合计">
        {inv.total_amount ? '¥' + inv.total_amount : '—'}
      </span>
      <CopyInvoiceFileButton invoiceId={inv.id} filename={inv.display_filename} />
    </li>
  )
}
