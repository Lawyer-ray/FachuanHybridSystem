import { useState } from 'react'
import { UserPlus, Trash2, Loader2, ShieldCheck } from 'lucide-react'
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

import { useAccessGrantMutations } from '../hooks/use-access-grant-mutations'
import type { CaseAccessGrant } from '../types'

export interface CaseAccessGrantSectionProps {
  grants: CaseAccessGrant[]
  editable?: boolean
  caseId?: number
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-8">
      <div className="bg-muted flex size-10 items-center justify-center rounded-full">
        <ShieldCheck className="text-muted-foreground size-5" />
      </div>
      <p className="text-muted-foreground mt-3 text-sm">暂无额外授权</p>
    </div>
  )
}

export function CaseAccessGrantSection({ grants, editable, caseId }: CaseAccessGrantSectionProps) {
  const [addOpen, setAddOpen] = useState(false)
  const [granteeId, setGranteeId] = useState('')

  const mutations = useAccessGrantMutations(caseId ?? 0)

  const handleAdd = () => {
    if (!caseId || !granteeId.trim()) return
    const id = parseInt(granteeId.trim(), 10)
    if (isNaN(id)) {
      toast.error('请输入有效的律师 ID')
      return
    }
    mutations.createGrant.mutate(
      { case_id: caseId, grantee_id: id },
      {
        onSuccess: () => {
          toast.success('授权成功')
          setAddOpen(false)
          setGranteeId('')
        },
        onError: (e) => toast.error(e.message || '授权失败'),
      },
    )
  }

  const handleDelete = (id: number) => {
    mutations.deleteGrant.mutate(id, {
      onSuccess: () => toast.success('已撤销授权'),
      onError: (e) => toast.error(e.message || '撤销失败'),
    })
  }

  return (
    <div className="space-y-3">
      {editable && caseId && (
        <div className="flex justify-end">
          <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
            <UserPlus className="mr-1 size-3" /> 添加授权
          </Button>
          <Dialog open={addOpen} onOpenChange={setAddOpen}>
            <DialogContent className="sm:max-w-sm">
              <DialogHeader>
                <DialogTitle>授权律师查看案件</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-2">
                  <Label>律师 ID</Label>
                  <Input
                    type="number"
                    placeholder="输入律师 ID"
                    value={granteeId}
                    onChange={(e) => setGranteeId(e.target.value)}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setAddOpen(false)}>取消</Button>
                <Button onClick={handleAdd} disabled={!granteeId.trim() || mutations?.createGrant.isPending}>
                  {mutations?.createGrant.isPending && <Loader2 className="mr-1 size-3 animate-spin" />}
                  确认授权
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      )}

      {grants.length === 0 ? (
        <EmptyState />
      ) : (
        grants.map((g) => {
          const name = g.grantee_detail?.real_name || g.grantee_detail?.username || '未知律师'
          const phone = g.grantee_detail?.phone

          return (
            <Card key={g.id} className="gap-0 py-0">
              <CardHeader className="py-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <ShieldCheck className="text-muted-foreground size-4 shrink-0" />
                    <span className="text-sm font-medium truncate">{name}</span>
                    {phone && <span className="text-xs text-muted-foreground">{phone}</span>}
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
                          <AlertDialogTitle>确认撤销授权</AlertDialogTitle>
                          <AlertDialogDescription>
                            确定要撤销「{name}」的案件查看权限吗？
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>取消</AlertDialogCancel>
                          <AlertDialogAction variant="destructive" onClick={() => handleDelete(g.id)}>
                            撤销
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  )}
                </div>
              </CardHeader>
            </Card>
          )
        })
      )}
    </div>
  )
}

export default CaseAccessGrantSection
