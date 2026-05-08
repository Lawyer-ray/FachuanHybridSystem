import { useState, useCallback } from 'react'
import { Trash2, Image, DollarSign, Receipt } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { contractApi } from '../api'
import type { Contract, ClientPaymentRecord } from '../types'
import { FEE_MODE_LABELS, type FeeMode } from '../types'
import { PaymentList } from './PaymentList'
import { resolveMediaUrl } from '@/lib/api'
import { formatAmountInt } from '@/lib/format'

function DetailField({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <div className="text-muted-foreground mb-0.5 text-xs">{label}</div>
      <div className={`text-[13px] ${mono ? 'font-mono' : ''}`}>{value || '—'}</div>
    </div>
  )
}

function DetailCard({ title, children, extra }: { title: string; children: React.ReactNode; extra?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border/60 p-[18px] mb-4 bg-card">
      <div className="flex items-center justify-between mb-3.5">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        {extra}
      </div>
      {children}
    </div>
  )
}

function ClientPaymentSection({ contractId, records: initial }: { contractId: number; records: ClientPaymentRecord[] }) {
  const [records, setRecords] = useState(initial)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const total = records.reduce((s, r) => s + r.amount, 0)

  const handleDelete = useCallback(async () => {
    if (deleteId == null) return
    try {
      await contractApi.deleteClientPaymentRecord(contractId, deleteId)
      setRecords(prev => prev.filter(r => r.id !== deleteId))
      toast.success('已删除')
    } catch { toast.error('删除失败') }
    setDeleteId(null)
  }, [contractId, deleteId])

  return (
    <DetailCard
      title="客户付款凭证"
      extra={records.length > 0 ? <span className="text-muted-foreground text-xs">{records.length} 笔 · {formatAmountInt(total)}</span> : undefined}
    >
      {records.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8">
          <DollarSign className="text-muted-foreground mb-2 size-6 opacity-40" />
          <p className="text-muted-foreground text-[13px]">暂无客户付款凭证</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {records.map(r => (
            <div key={r.id} className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-2.5 text-[13px] group">
              <span className="text-sm font-semibold text-green-600 min-w-[100px]">{formatAmountInt(r.amount)}</span>
              <span className="text-muted-foreground text-xs flex-1">{r.note || ''}</span>
              <span className="text-muted-foreground text-xs">{r.created_at?.slice(0, 10) || ''}</span>
              {r.image_path && (
                <a href={resolveMediaUrl(r.image_path) || '#'} target="_blank" rel="noopener noreferrer" className="text-primary">
                  <Image className="size-3.5" />
                </a>
              )}
              <Button variant="ghost" size="icon" className="size-6 opacity-0 group-hover:opacity-100 text-destructive" onClick={() => setDeleteId(r.id)}>
                <Trash2 className="size-3" />
              </Button>
            </div>
          ))}
        </div>
      )}

      <AlertDialog open={deleteId != null} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>删除后无法恢复。</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground">删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </DetailCard>
  )
}

function InvoiceSection({ contract }: { contract: Contract }) {
  const allInvoices = contract.payments.flatMap(p => (p.invoices ?? []).map(inv => ({ ...inv, paymentAmount: p.amount })))

  if (allInvoices.length === 0) return null

  return (
    <DetailCard title="发票记录" extra={<span className="text-muted-foreground text-xs">{allInvoices.length} 张</span>}>
      <div className="flex flex-col gap-2">
        {allInvoices.map(inv => (
          <div key={inv.id} className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-2.5 text-[13px]">
            <Receipt className="size-3.5 text-muted-foreground shrink-0" />
            <span className="flex-1 truncate">{inv.original_filename}</span>
            {inv.invoice_number && <span className="text-muted-foreground text-xs font-mono">#{inv.invoice_number}</span>}
            {inv.total_amount != null && <span className="text-xs font-mono">{formatAmountInt(inv.total_amount)}</span>}
            <span className="text-muted-foreground text-xs">{inv.uploaded_at?.slice(0, 10) || ''}</span>
          </div>
        ))}
      </div>
    </DetailCard>
  )
}

export function FeesTab({ contract: c }: { contract: Contract }) {
  const feeLabel = FEE_MODE_LABELS[c.fee_mode as FeeMode] ?? c.fee_mode

  const hasProgress = c.fixed_amount != null && c.fixed_amount > 0
  const paymentPercent = hasProgress ? Math.min(100, Math.round((c.total_received / c.fixed_amount!) * 100)) : 0
  const invoicePercent = c.total_received > 0 ? Math.min(100, Math.round((c.total_invoiced / c.total_received) * 100)) : 0

  return (
    <div>
      {/* Fee Terms */}
      <DetailCard title="收费条款">
        <div className="grid gap-[14px] sm:grid-cols-2 lg:grid-cols-3">
          <DetailField label="收费模式" value={
            <Badge variant="outline" className="text-[11px] px-2 py-0.5">{feeLabel}</Badge>
          } />
          {c.fixed_amount != null && (
            <DetailField label="固定/前期律师费" value={`${formatAmountInt(c.fixed_amount)}`} mono />
          )}
          {c.risk_rate != null && (
            <DetailField label="风险比例" value={`${c.risk_rate}%`} mono />
          )}
          {c.custom_terms && (
            <DetailField label="自定义条款" value={c.custom_terms} />
          )}
        </div>
      </DetailCard>

      {/* Collection Progress */}
      <DetailCard title="收款进度">
        <div className="grid gap-8 lg:grid-cols-2">
          <div>
            <div className="flex items-center justify-between text-xs mb-1.5">
              <span className="text-muted-foreground">收款进度</span>
              <span className="font-semibold">{paymentPercent}%</span>
            </div>
            <div className="h-2 bg-muted rounded-full overflow-hidden mb-2">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(paymentPercent, 100)}%`,
                  backgroundColor: paymentPercent >= 100 ? '#22c55e' : 'var(--primary)',
                }}
              />
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">应收 {hasProgress ? `¥${c.fixed_amount!.toLocaleString()}` : '—'}</span>
              <span className="text-green-600 font-medium">已收 {formatAmountInt(c.total_received)}</span>
            </div>
            {c.unpaid_amount != null && c.unpaid_amount > 0 && (
              <div className="mt-1 text-xs text-red-600">未收 {formatAmountInt(c.unpaid_amount)}</div>
            )}
            {paymentPercent >= 100 && (
              <div className="mt-1.5">
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-green-50 text-green-700">已收齐</span>
              </div>
            )}
          </div>

          <div>
            <div className="flex items-center justify-between text-xs mb-1.5">
              <span className="text-muted-foreground">开票进度</span>
              <span className="font-semibold">{invoicePercent}%</span>
            </div>
            <div className="h-2 bg-muted rounded-full overflow-hidden mb-2">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(invoicePercent, 100)}%`,
                  backgroundColor: invoicePercent >= 100 ? '#22c55e' : 'var(--primary)',
                }}
              />
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">已收 {formatAmountInt(c.total_received)}</span>
              <span className="text-green-600 font-medium">已开票 {formatAmountInt(c.total_invoiced)}</span>
            </div>
            {invoicePercent < 100 && c.total_received > 0 && (
              <div className="mt-1.5">
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700">待开票</span>
              </div>
            )}
          </div>
        </div>
      </DetailCard>

      {/* Payment Records */}
      <div className="rounded-lg border border-border/60 p-[18px] mb-4 bg-card">
        <PaymentList contractId={c.id} payments={c.payments} />
      </div>

      {/* Invoices */}
      <InvoiceSection contract={c} />

      {/* Client Payment Records */}
      <ClientPaymentSection contractId={c.id} records={c.client_payment_records ?? []} />
    </div>
  )
}
