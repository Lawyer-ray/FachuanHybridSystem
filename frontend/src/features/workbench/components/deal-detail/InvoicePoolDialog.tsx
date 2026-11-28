import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { errMessage } from '@/lib/errors'
import { contractInvoiceKeys, deletePaymentInvoice, listContractInvoices, uploadContractInvoices } from '../../api'
import { CopyInvoiceFileButton, InvoiceDropZone } from './PaymentInvoiceZone'

/**
 * 合同发票弹窗（右栏「＋ 传发票」）：**先开票后付款**的入口。
 *
 * 钱还没到就能把票传进来挂在合同名下；这里也管理这些尚未关联收款的票（删除）。
 * 关联动作不在这做——记完收款，在记收款弹窗里对着金额一键关联更顺手。
 */
export function InvoicePoolDialog({
  open,
  contractId,
  onClose,
}: {
  open: boolean
  contractId: number
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [uploading, setUploading] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  /**
   * 待确认删除的发票 id。
   *
   * 原来点一下垃圾桶就删：记录 + 磁盘文件一起没（后端 `invoice_file_service`
   * 连 media 一起删），没有撤销。同一页的文件夹删除却是「行内确认 + 移入
   * _已删除可找回」——同一个「删除」两套口径，用户当然会按错。
   */
  const [confirmId, setConfirmId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const poolQ = useQuery({
    queryKey: contractInvoiceKeys.unlinked(contractId),
    queryFn: () => listContractInvoices(contractId, true),
    enabled: open,
    staleTime: 30_000,
  })
  const pool = poolQ.data ?? []

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: contractInvoiceKeys.all(contractId) })
  }

  const doUpload = async (files: File[]) => {
    if (files.length === 0) return
    setUploading(true)
    setError(null)
    try {
      const result = await uploadContractInvoices(contractId, files)
      if (result.failed.length) {
        setError(result.failed.map((f) => `${f.filename}：${f.reason}`).join('；'))
      }
      if (result.duplicated_count > 0) {
        toast.warning(`${result.duplicated_count} 张发票号已存在，未重复计入`)
      }
      if (result.saved.length) {
        toast.success(`已传 ${result.saved.length} 张发票到合同名下`)
        refresh()
      }
    } catch (e) {
      setError(errMessage(e, '发票上传失败，请重试'))
    } finally {
      setUploading(false)
    }
  }

  const doDelete = async (invoiceId: number) => {
    setDeletingId(invoiceId)
    setError(null)
    try {
      await deletePaymentInvoice(invoiceId)
      toast.success('发票已删除')
      setConfirmId(null)
      refresh()
    } catch (e) {
      setError(errMessage(e, '删除失败，请重试'))
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="grid-cols-[minmax(0,1fr)] gap-0 p-6 sm:max-w-[560px]">
        <DialogHeader className="pb-3">
          <DialogTitle className="text-[15px]">传发票</DialogTitle>
        </DialogHeader>

        <p className="mb-3 text-[11.5px] leading-[1.6] text-muted-foreground">
          先开票、后收款的流程走这里：票先挂合同名下（不动开票金额），钱到账记完收款后，
          在记收款弹窗里一键关联到那笔收款。
        </p>

        <InvoiceDropZone
          uploading={uploading}
          dragHint="上传到合同（未归属收款）"
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

        {poolQ.isPending && <p className="mt-3 text-[11.5px] text-muted-foreground">正在读取发票…</p>}
        {poolQ.isError && (
          <p className="mt-3 flex flex-wrap items-center gap-2 text-[11.5px] text-muted-foreground">
            发票列表读取失败
            <button
              type="button"
              className="cursor-pointer underline underline-offset-2 hover:text-foreground"
              onClick={() => void poolQ.refetch()}
            >
              重试
            </button>
          </p>
        )}

        {pool.length > 0 && (
          <div className="mt-3">
            <div className="mb-1 text-[11px] font-[650] text-muted-foreground">未关联收款 · {pool.length} 张</div>
            <ul className="flex flex-col gap-1">
              {pool.map((inv) => (
                <li key={inv.id} className="flex items-center gap-2 rounded-[6px] bg-secondary/50 px-2 py-1 text-[11.5px]">
                  <span className="min-w-0 flex-1 truncate" title={inv.display_filename}>
                    {inv.display_filename}
                  </span>
                  <span className="font-[620] tabular-nums">{inv.total_amount ? '¥' + inv.total_amount : '金额未识别'}</span>
                  <CopyInvoiceFileButton invoiceId={inv.id} filename={inv.display_filename} />
                  {confirmId === inv.id ? (
                    <span className="flex flex-none items-center gap-1">
                      <span className="text-[10.5px] text-status-red" title="记录与磁盘上的文件都会被删除，不能撤销">
                        删除？
                      </span>
                      <button
                        type="button"
                        className="rounded-[5px] bg-status-red px-1.5 py-0.5 text-[10.5px] font-[620] text-white"
                        disabled={deletingId != null}
                        onClick={() => void doDelete(inv.id)}
                      >
                        {deletingId === inv.id ? <Loader2 className="size-3 animate-spin" /> : '删除'}
                      </button>
                      <button
                        type="button"
                        className="rounded-[5px] px-1.5 py-0.5 text-[10.5px] text-muted-foreground hover:bg-secondary"
                        disabled={deletingId != null}
                        onClick={() => setConfirmId(null)}
                      >
                        取消
                      </button>
                    </span>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-[22px] px-1.5 text-muted-foreground hover:text-status-red"
                      disabled={deletingId != null}
                      title="删除这张发票（记录与文件都会被删除）"
                      aria-label="删除这张发票"
                      onClick={() => setConfirmId(inv.id)}
                    >
                      <Trash2 className="size-3" />
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
