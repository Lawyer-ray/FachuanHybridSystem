import { useState } from 'react'
import { UserCheck, Phone, Plus, Trash2, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { Card, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'

import { useAssignmentMutations } from '../hooks/use-assignment-mutations'
import type { CaseAssignment } from '../types'

export interface CaseAssignmentSectionProps {
  assignments: CaseAssignment[]
  editable?: boolean
  caseId?: number
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-8">
      <div className="bg-muted flex size-10 items-center justify-center rounded-full">
        <UserCheck className="text-muted-foreground size-5" />
      </div>
      <p className="text-muted-foreground mt-3 text-sm">暂无指派律师</p>
    </div>
  )
}

export function CaseAssignmentSection({ assignments, editable, caseId }: CaseAssignmentSectionProps) {
  const [addOpen, setAddOpen] = useState(false)
  const [lawyerId, setLawyerId] = useState('')

  const mutations = useAssignmentMutations(caseId ?? 0)

  const handleAdd = () => {
    if (!caseId || !lawyerId.trim()) return
    const id = parseInt(lawyerId.trim(), 10)
    if (isNaN(id)) {
      toast.error('请输入有效的律师 ID')
      return
    }
    mutations.createAssignment.mutate(
      { case_id: caseId, lawyer_id: id },
      {
        onSuccess: () => {
          toast.success('添加律师成功')
          setAddOpen(false)
          setLawyerId('')
        },
        onError: (e) => toast.error(e.message || '添加失败'),
      },
    )
  }

  const handleDelete = (id: number) => {
    mutations.deleteAssignment.mutate(id, {
      onSuccess: () => toast.success('删除成功'),
      onError: (e) => toast.error(e.message || '删除失败'),
    })
  }

  return (
    <div className="space-y-3">
      {editable && caseId && (
        <div className="flex justify-end">
          <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
            <Plus className="mr-1 size-3" /> 添加律师
          </Button>
          <Dialog open={addOpen} onOpenChange={setAddOpen}>
            <DialogContent className="sm:max-w-sm">
              <DialogHeader>
                <DialogTitle>添加指派律师</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-2">
                  <Label>律师 ID</Label>
                  <Input
                    type="number"
                    placeholder="输入律师 ID"
                    value={lawyerId}
                    onChange={(e) => setLawyerId(e.target.value)}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setAddOpen(false)}>取消</Button>
                <Button onClick={handleAdd} disabled={!lawyerId.trim() || mutations?.createAssignment.isPending}>
                  {mutations?.createAssignment.isPending && <Loader2 className="mr-1 size-3 animate-spin" />}
                  确认
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      )}

      {assignments.length === 0 ? (
        <EmptyState />
      ) : (
        assignments.map((a) => {
          const name = a.lawyer_detail?.real_name || a.lawyer_detail?.username || '未知律师'
          const phone = a.lawyer_detail?.phone

          return (
            <Card key={a.id} className="gap-0 py-0">
              <CardHeader className="py-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <UserCheck className="text-muted-foreground size-4 shrink-0" />
                    <span className="text-sm font-medium truncate">{name}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    {phone && (
                      <div className="flex items-center gap-1 text-muted-foreground shrink-0">
                        <Phone className="size-3" />
                        <span className="text-xs">{phone}</span>
                      </div>
                    )}
                    {editable && caseId && (
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="icon-xs">
                            <Trash2 className="text-muted-foreground size-3" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent size="sm">
                          <AlertDialogHeader>
                            <AlertDialogTitle>确认移除</AlertDialogTitle>
                            <AlertDialogDescription>
                              确定要移除律师「{name}」的指派吗？
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>取消</AlertDialogCancel>
                            <AlertDialogAction variant="destructive" onClick={() => handleDelete(a.id)}>
                              移除
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    )}
                  </div>
                </div>
              </CardHeader>
            </Card>
          )
        })
      )}
    </div>
  )
}

export default CaseAssignmentSection
