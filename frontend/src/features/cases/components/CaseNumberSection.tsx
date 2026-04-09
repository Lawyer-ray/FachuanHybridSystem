/**
 * CaseNumberSection - 案号列表区块
 *
 * Requirements: 3.9, 5.8
 */

import { useState } from 'react'
import { Hash, Clock, Plus, Trash2, Loader2 } from 'lucide-react'
import { format } from 'date-fns'
import { toast } from 'sonner'

import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'

import { useCaseNumberMutations } from '../hooks/use-case-number-mutations'
import type { CaseNumber } from '../types'

export interface CaseNumberSectionProps {
  caseNumbers: CaseNumber[]
  editable?: boolean
  caseId?: number
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  try {
    return format(new Date(dateStr), 'yyyy-MM-dd')
  } catch {
    return dateStr
  }
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-8">
      <div className="bg-muted flex size-10 items-center justify-center rounded-full">
        <Hash className="text-muted-foreground size-5" />
      </div>
      <p className="text-muted-foreground mt-3 text-sm">暂无案号</p>
    </div>
  )
}

export function CaseNumberSection({ caseNumbers, editable, caseId }: CaseNumberSectionProps) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [newNumber, setNewNumber] = useState('')
  const [newRemarks, setNewRemarks] = useState('')

  const mutations = caseId ? useCaseNumberMutations(caseId) : null

  const handleAdd = () => {
    if (!mutations || !caseId || !newNumber.trim()) return
    mutations.createCaseNumber.mutate(
      { case_id: caseId, number: newNumber.trim(), remarks: newRemarks.trim() || undefined },
      {
        onSuccess: () => {
          toast.success('添加案号成功')
          setDialogOpen(false)
          setNewNumber('')
          setNewRemarks('')
        },
        onError: (e) => toast.error(e.message || '添加失败'),
      },
    )
  }

  const handleDelete = (id: number) => {
    if (!mutations) return
    mutations.deleteCaseNumber.mutate(id, {
      onSuccess: () => toast.success('删除成功'),
      onError: (e) => toast.error(e.message || '删除失败'),
    })
  }

  return (
    <div className="space-y-3">
      {editable && caseId && (
        <div className="flex justify-end">
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline">
                <Plus className="mr-1 size-3" /> 添加案号
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>添加案号</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium">案号</label>
                  <Input
                    placeholder="请输入案号"
                    value={newNumber}
                    onChange={(e) => setNewNumber(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">备注</label>
                  <Input
                    placeholder="备注（可选）"
                    value={newRemarks}
                    onChange={(e) => setNewRemarks(e.target.value)}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  onClick={handleAdd}
                  disabled={!newNumber.trim() || mutations?.createCaseNumber.isPending}
                >
                  {mutations?.createCaseNumber.isPending && <Loader2 className="mr-1 size-3 animate-spin" />}
                  确认
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      )}

      {caseNumbers.length === 0 ? (
        <EmptyState />
      ) : (
        caseNumbers.map((cn) => (
          <Card key={cn.id} className="gap-0 py-0">
            <CardHeader className="pb-0 pt-4">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <Hash className="text-muted-foreground size-4 shrink-0" />
                  <span className="text-sm font-medium truncate">{cn.number}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1 text-muted-foreground shrink-0">
                    <Clock className="size-3" />
                    <span className="text-xs">{formatDate(cn.created_at)}</span>
                  </div>
                  {editable && caseId && (
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="ghost" size="icon-xs">
                          <Trash2 className="text-muted-foreground size-3" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent size="sm">
                        <AlertDialogHeader>
                          <AlertDialogTitle>确认删除</AlertDialogTitle>
                          <AlertDialogDescription>
                            确定要删除案号「{cn.number}」吗？
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>取消</AlertDialogCancel>
                          <AlertDialogAction variant="destructive" onClick={() => handleDelete(cn.id)}>
                            删除
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  )}
                </div>
              </div>
            </CardHeader>
            {cn.remarks && (
              <CardContent className="pb-4 pt-2">
                <p className="text-muted-foreground text-xs">{cn.remarks}</p>
              </CardContent>
            )}
          </Card>
        ))
      )}
    </div>
  )
}

export default CaseNumberSection
