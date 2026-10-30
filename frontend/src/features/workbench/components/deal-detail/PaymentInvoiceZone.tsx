import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Link2, Loader2, Upload } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { copyText } from '@/lib/clipboard'
import { errMessage } from '@/lib/errors'
import {
  attachPaymentInvoice,
  contractInvoiceKeys,
  copyInvoiceToClipboard,
  listContractInvoices,
  listPaymentInvoices,
  uploadContractInvoices,
  uploadPaymentInvoices,
  type PaymentInvoice,
} from '../../api'

/**
 * 记收款弹窗第③节「发票」：两种真实流程在这里汇合。
 *
 * - **先付款后开票**（常规）：保存收款后拖票进来，直接挂这笔收款；
 * - **先开票后付款**：收款还没保存（或还没记）就能拖票——票先挂合同名下，
 *   保存收款后下方列出还没归属到具体某笔收款的票，点「关联」把票挂到这笔收款上；
 *   金额与收款相同的行加「金额吻合」提示，帮律师一眼对上。
 */

const PAYMENT_INVOICES_KEY = (paymentId: number) => ['payment-invoices', paymentId] as const

export function PaymentInvoiceZone({
  contractId,
  paymentId,
  paymentAmount,
  onChanged,
}: {
  contractId: number
  /** null = 收款还没保存：此阶段拖票走「先开票」路径（挂合同，不归属某笔收款） */
  paymentId: number | null
  /** 当前收款金额（识别/手填），用于未关联行的金额吻合提示 */
  paymentAmount: number | null
  /** 上传/关联成功：让页面刷新合同（统计条、收款行、未关联计数都跟着变） */
  onChanged: () => void
}) {
  const qc = useQueryClient()
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [attachingId, setAttachingId] = useState<number | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const saved = paymentId != null
  const paymentInvoicesQ = useQuery({
    queryKey: PAYMENT_INVOICES_KEY(paymentId ?? 0),
    queryFn: () => listPaymentInvoices(paymentId as number, contractId),
    enabled: saved,
    staleTime: 30_000,
  })
  const poolQ = useQuery({
    queryKey: contractInvoiceKeys.unlinked(contractId),
    queryFn: () => listContractInvoices(contractId, true),
    staleTime: 30_000,
  })
  const paymentInvoices = saved ? (paymentInvoicesQ.data ?? []) : []
  const pool = poolQ.data ?? []

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: contractInvoiceKeys.all(contractId) })
    if (paymentId != null) void qc.invalidateQueries({ queryKey: PAYMENT_INVOICES_KEY(paymentId) })
    onChanged()
  }

  const doUpload = async (files: File[]) => {
    if (files.length === 0) return
    setUploading(true)
    setError(null)
    try {
      const result = saved
        ? await uploadPaymentInvoices(paymentId, files)
        : await uploadContractInvoices(contractId, files)
      if (result.failed.length) {
        setError(result.failed.map((f) => `${f.filename}：${f.reason}`).join('；'))
      }
      if (result.duplicated_count > 0) {
        toast.warning(`${result.duplicated_count} 张发票号已存在，未重复计入开票金额`)
      }
      if (result.saved.length) {
        toast.success(
          saved
            ? `已识别并归档 ${result.saved.length} 张发票`
            : `已传 ${result.saved.length} 张发票到合同名下，收款后可关联`,
        )
        refresh()
      }
    } catch (e) {
      setError(errMessage(e, '发票上传失败，请重试'))
    } finally {
      setUploading(false)
    }
  }

  const doAttach = async (invoice: PaymentInvoice) => {
    if (paymentId == null) return
    setAttachingId(invoice.id)
    setError(null)
    try {
      await attachPaymentInvoice(invoice.id, paymentId)
      toast.success('发票已关联到这笔收款')
      refresh()
    } catch (e) {
      setError(errMessage(e, '关联失败，请重试'))
    } finally {
      setAttachingId(null)
    }
  }

  return (
    <section className="pt-4">
      <div className="mb-1.5 flex items-baseline gap-2">
        <span className="text-[12px] font-[650]">发票</span>
        <span className="text-[11px] text-muted-foreground">
          {saved ? '拖入或点击上传，直接归到这笔收款' : '钱没到也能先传——票挂合同名下，保存收款后一键关联'}
        </span>
      </div>

      <InvoiceDropZone
        uploading={uploading}
        dragHint={saved ? undefined : '上传到合同（未归属收款）'}
        onClick={() => fileRef.current?.click()}
        onFiles={(files) => void doUpload(files)}
      />
      <input
        ref={fileRef}
        type="file"
        multiple
        accept=".pdf,.jpg,.jpeg,.png"
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          e.target.value = ''
          if (files.length) void doUpload(files)
        }}
      />

      {error && <p className="mt-2 text-[11.5px] break-words text-status-red">{error}</p>}

      {saved && pool.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[11px] font-[650] text-muted-foreground">
            合同下未关联收款的发票 · {pool.length} 张
          </div>
          <ul className="flex flex-col gap-1">
            {pool.map((inv) => (
              <li
                key={inv.id}
                className="flex items-center gap-2 rounded-[6px] border border-border-light bg-secondary/40 px-2 py-1 text-[11.5px]"
              >
                <span className="min-w-0 flex-1 truncate" title={inv.display_filename}>
                  {inv.display_filename}
                </span>
                {inv.total_amount && paymentAmount != null && Number(inv.total_amount) === paymentAmount && (
                  <span className="flex-none rounded-[5px] bg-status-green/12 px-1.5 py-px text-[10px] font-[620] text-status-green">
                    金额吻合
                  </span>
                )}
                <CopyInvoiceFileButton invoiceId={inv.id} filename={inv.display_filename} />
                <Button
                  size="sm"
                  variant="outline"
                  className="h-[22px] px-2 text-[11px]"
                  disabled={attachingId != null}
                  onClick={() => void doAttach(inv)}
                >
                  {attachingId === inv.id ? <Loader2 className="size-3 animate-spin" /> : <Link2 className="size-3" />}
                  关联
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {paymentInvoices.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[11px] font-[650] text-muted-foreground">这笔收款的发票</div>
          <ul className="flex flex-col gap-1">
            {paymentInvoices.map((inv) => (
              <li key={inv.id} className="flex items-center gap-2 rounded-[6px] bg-secondary/50 px-2 py-1 text-[11.5px]">
                <span className="min-w-0 flex-1 truncate" title={inv.display_filename}>
                  {inv.display_filename}
                </span>
                <span className="font-[620] tabular-nums">{inv.total_amount ? '¥' + inv.total_amount : '金额未识别'}</span>
                <CopyInvoiceFileButton invoiceId={inv.id} filename={inv.display_filename} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

/** 复制重命名后的发票文件本体（与短信文书同一套链路，微信 ⌘V 直接粘出文件）
 *
 * 后端 NSPasteboard 落板（同 Finder ⌘C）；环境不支持时降级复制文件名并如实提示。 */
export function CopyInvoiceFileButton({ invoiceId, filename }: { invoiceId: number; filename: string }) {
  const [busy, setBusy] = useState(false)
  const onClick = async () => {
    if (busy) return
    setBusy(true)
    // busy 必须在 finally 里收：落板成功走 return 也要清掉，否则图标一直转圈
    // （曾因 return 前忘记复位，表现成「复制成功了但按钮永远在转」）。
    try {
      const res = await copyInvoiceToClipboard(invoiceId)
      if (res.success && res.copied > 0) {
        toast.success('发票文件已复制，微信对话框直接 ⌘V 粘贴发送')
        return
      }
      // 落板失败（文件缺失等）：文件名兜底，粘到对话里至少能对上文件
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
      title={`复制文件（${filename}）`}
      className="flex-none rounded-[5px] p-1 text-muted-foreground/70 transition-colors hover:bg-secondary hover:text-foreground"
      onClick={() => void onClick()}
    >
      {busy ? <Loader2 className="size-3 animate-spin" /> : <Copy className="size-3" />}
    </button>
  )
}

/** 拖放/点击上传区（记收款弹窗与合同发票弹窗共用；compact 供右栏窄条用） */
export function InvoiceDropZone({
  uploading,
  dragHint,
  compact = false,
  onClick,
  onFiles,
}: {
  uploading: boolean
  /** 右上角补充说明（如「上传到合同（未归属收款）」）；不传则不渲染 */
  dragHint?: string
  /** 紧凑形态：右栏/空态用，高度与文案收一档 */
  compact?: boolean
  onClick: () => void
  onFiles: (files: File[]) => void
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
      onDragOver={(e) => {
        e.preventDefault()
        e.currentTarget.dataset.drag = '1'
      }}
      onDragLeave={(e) => delete e.currentTarget.dataset.drag}
      onDrop={(e) => {
        e.preventDefault()
        delete e.currentTarget.dataset.drag
        const files = Array.from(e.dataTransfer.files)
        if (files.length) onFiles(files)
      }}
      className={
        'flex cursor-pointer flex-col items-center gap-1 rounded-[10px] border border-dashed border-border text-[12px] transition-colors hover:border-ring/50 hover:bg-secondary/40 data-[drag]:border-foreground data-[drag]:bg-secondary ' +
        (compact ? 'py-2.5' : 'py-5')
      }
    >
      <div className="flex items-center gap-1.5">
        {uploading ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : <Upload className="size-4 text-muted-foreground" />}
        <span>{uploading ? '正在识别发票…' : compact ? '拖入或点击上传发票（自动识别、归档、重命名）' : '把发票拖到这里，或点击选择'}</span>
        {dragHint && <span className="text-[10.5px] text-muted-foreground/70">（{dragHint}）</span>}
      </div>
      {!compact && <span className="text-[10.5px] text-muted-foreground/70">支持 PDF / JPG / PNG，单张 ≤ 20MB</span>}
    </div>
  )
}
