import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { INVOICE_STATUS_LABELS, type ContractPayment, type InvoiceStatus } from '../types'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  payment?: ContractPayment
  contractId: number
  onSubmit: (data: { amount: number; received_at?: string; invoice_status?: InvoiceStatus; invoiced_amount?: number; note?: string; contract_id: number; confirm: boolean }) => void
  submitting?: boolean
}

export function PaymentFormDialog({ open, onOpenChange, payment, contractId, onSubmit, submitting }: Props) {
  const [amount, setAmount] = useState('')
  const [receivedAt, setReceivedAt] = useState('')
  const [invoiceStatus, setInvoiceStatus] = useState<InvoiceStatus>('UNINVOICED')
  const [invoicedAmount, setInvoicedAmount] = useState('')
  const [note, setNote] = useState('')

  useEffect(() => {
    if (payment) {
      setAmount(String(payment.amount))
      setReceivedAt(payment.received_at ?? '')
      setInvoiceStatus(payment.invoice_status)
      setInvoicedAmount(String(payment.invoiced_amount))
      setNote(payment.note ?? '')
    } else {
      setAmount(''); setReceivedAt(''); setInvoiceStatus('UNINVOICED'); setInvoicedAmount(''); setNote('')
    }
  }, [payment, open])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit({
      contract_id: contractId,
      amount: Number(amount),
      received_at: receivedAt || undefined,
      invoice_status: invoiceStatus,
      invoiced_amount: invoicedAmount ? Number(invoicedAmount) : undefined,
      note: note || undefined,
      confirm: true,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>{payment ? '编辑收款' : '新增收款'}</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label>收款金额 *</Label>
            <Input type="number" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} required />
          </div>
          <div className="space-y-2">
            <Label>收款日期</Label>
            <Input type="date" value={receivedAt} onChange={e => setReceivedAt(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>开票状态</Label>
            <Select value={invoiceStatus} onValueChange={v => setInvoiceStatus(v as InvoiceStatus)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(INVOICE_STATUS_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>已开票金额</Label>
            <Input type="number" step="0.01" value={invoicedAmount} onChange={e => setInvoicedAmount(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>备注</Label>
            <Input value={note} onChange={e => setNote(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
            <Button type="submit" disabled={submitting || !amount}>{submitting ? '提交中...' : '保存'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
