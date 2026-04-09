import { useState, useCallback } from 'react'
import { Plus, Edit, Trash2, DollarSign } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { PaymentFormDialog } from './PaymentFormDialog'
import { usePaymentMutations } from '../hooks/use-payment-mutations'
import type { ContractPayment } from '../types'

export function PaymentList({ contractId, payments }: { contractId: number; payments: ContractPayment[] }) {
  const { createPayment, updatePayment, deletePayment } = usePaymentMutations(contractId)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<ContractPayment | undefined>()
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const handleSubmit = useCallback(async (data: Record<string, unknown>) => {
    try {
      if (editing) {
        const { contract_id, ...rest } = data as Record<string, unknown>
        await updatePayment.mutateAsync({ id: editing.id, data: rest as any })
        toast.success('收款已更新')
      } else {
        await createPayment.mutateAsync(data as any)
        toast.success('收款已添加')
      }
      setFormOpen(false); setEditing(undefined)
    } catch { toast.error('操作失败') }
  }, [editing, createPayment, updatePayment])

  const handleDelete = useCallback(async () => {
    if (deleteId == null) return
    try {
      await deletePayment.mutateAsync(deleteId)
      toast.success('收款已删除')
    } catch { toast.error('删除失败') }
    setDeleteId(null)
  }, [deleteId, deletePayment])

  const total = payments.reduce((s, p) => s + p.amount, 0)

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle className="flex items-center gap-2 text-base"><DollarSign className="size-4" />收款记录</CardTitle>
          <Button size="sm" onClick={() => { setEditing(undefined); setFormOpen(true) }}><Plus className="mr-1 size-4" />新增</Button>
        </CardHeader>
        <CardContent>
          {payments.length === 0 ? <p className="text-muted-foreground text-sm">暂无收款记录</p> : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>金额</TableHead>
                  <TableHead>收款日期</TableHead>
                  <TableHead>开票状态</TableHead>
                  <TableHead>已开票</TableHead>
                  <TableHead>备注</TableHead>
                  <TableHead className="w-[80px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {payments.map(p => (
                  <TableRow key={p.id}>
                    <TableCell className="font-mono">¥{p.amount.toLocaleString()}</TableCell>
                    <TableCell>{p.received_at || '-'}</TableCell>
                    <TableCell><Badge variant="outline" className="text-xs">{p.invoice_status_label}</Badge></TableCell>
                    <TableCell className="font-mono">¥{p.invoiced_amount.toLocaleString()}</TableCell>
                    <TableCell className="text-muted-foreground text-sm">{p.note || '-'}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="size-7" onClick={() => { setEditing(p); setFormOpen(true) }}>
                          <Edit className="size-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon" className="size-7 text-destructive" onClick={() => setDeleteId(p.id)}>
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                <TableRow>
                  <TableCell className="font-mono font-semibold">合计: ¥{total.toLocaleString()}</TableCell>
                  <TableCell colSpan={5} />
                </TableRow>
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <PaymentFormDialog
        open={formOpen} onOpenChange={setFormOpen}
        payment={editing} contractId={contractId}
        onSubmit={handleSubmit}
        submitting={createPayment.isPending || updatePayment.isPending}
      />

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
    </div>
  )
}
