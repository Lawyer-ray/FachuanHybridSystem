import { useState, useCallback } from 'react'
import { Plus, Edit, Trash2, FileText } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { AgreementFormDialog } from './AgreementFormDialog'
import { useAgreementMutations } from '../hooks/use-agreement-mutations'
import type { SupplementaryAgreement } from '../types'

export function SupplementaryAgreementList({ contractId, agreements }: { contractId: number; agreements: SupplementaryAgreement[] }) {
  const { createAgreement, updateAgreement, deleteAgreement } = useAgreementMutations(contractId)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<SupplementaryAgreement | undefined>()
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const handleSubmit = useCallback(async (data: { contract_id: number; name?: string; party_ids?: number[] }) => {
    try {
      if (editing) {
        const { contract_id, ...rest } = data
        await updateAgreement.mutateAsync({ id: editing.id, data: rest })
        toast.success('补充协议已更新')
      } else {
        await createAgreement.mutateAsync(data)
        toast.success('补充协议已添加')
      }
      setFormOpen(false); setEditing(undefined)
    } catch { toast.error('操作失败') }
  }, [editing, createAgreement, updateAgreement])

  const handleDelete = useCallback(async () => {
    if (deleteId == null) return
    try {
      await deleteAgreement.mutateAsync(deleteId)
      toast.success('补充协议已删除')
    } catch { toast.error('删除失败') }
    setDeleteId(null)
  }, [deleteId, deleteAgreement])

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle className="flex items-center gap-2 text-base"><FileText className="size-4" />补充协议</CardTitle>
          <Button size="sm" onClick={() => { setEditing(undefined); setFormOpen(true) }}><Plus className="mr-1 size-4" />新增</Button>
        </CardHeader>
        <CardContent>
          {agreements.length === 0 ? <p className="text-muted-foreground text-sm">暂无补充协议</p> : (
            <div className="space-y-3">
              {agreements.map(a => (
                <div key={a.id} className="flex items-center justify-between rounded-md border p-3">
                  <div>
                    <p className="text-sm font-medium">{a.name || `补充协议 #${a.id}`}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {a.parties.map(p => (
                        <Badge key={p.id} variant="outline" className="text-xs">
                          {p.client_name} ({p.role_label})
                        </Badge>
                      ))}
                    </div>
                    <p className="text-muted-foreground mt-1 text-xs">创建: {a.created_at?.slice(0, 10)}</p>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" className="size-7" onClick={() => { setEditing(a); setFormOpen(true) }}>
                      <Edit className="size-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon" className="size-7 text-destructive" onClick={() => setDeleteId(a.id)}>
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <AgreementFormDialog
        open={formOpen} onOpenChange={setFormOpen}
        agreement={editing} contractId={contractId}
        onSubmit={handleSubmit}
        submitting={createAgreement.isPending || updateAgreement.isPending}
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
