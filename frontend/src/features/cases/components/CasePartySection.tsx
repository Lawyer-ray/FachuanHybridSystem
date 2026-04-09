/**
 * CasePartySection - 当事人列表区块
 *
 * Requirements: 3.6, 5.5
 */

import { useState } from 'react'
import { Link } from 'react-router'
import { Users, ExternalLink, Plus, Trash2, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { Card, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'

import { generatePath } from '@/routes/paths'
import { usePartyMutations } from '../hooks/use-party-mutations'
import { LEGAL_STATUS_LABELS } from '../types'
import type { CaseParty } from '../types'

export interface CasePartySectionProps {
  parties: CaseParty[]
  editable?: boolean
  caseId?: number
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-8">
      <div className="bg-muted flex size-10 items-center justify-center rounded-full">
        <Users className="text-muted-foreground size-5" />
      </div>
      <p className="text-muted-foreground mt-3 text-sm">暂无当事人</p>
    </div>
  )
}

export function CasePartySection({ parties, editable, caseId }: CasePartySectionProps) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [newClientId, setNewClientId] = useState('')
  const [newLegalStatus, setNewLegalStatus] = useState('')

  const mutations = caseId ? usePartyMutations(caseId) : null

  const handleAdd = () => {
    if (!mutations || !caseId || !newClientId) return
    mutations.createParty.mutate(
      { case_id: caseId, client_id: Number(newClientId), legal_status: newLegalStatus || undefined },
      {
        onSuccess: () => {
          toast.success('添加当事人成功')
          setDialogOpen(false)
          setNewClientId('')
          setNewLegalStatus('')
        },
        onError: (e) => toast.error(e.message || '添加失败'),
      },
    )
  }

  const handleDelete = (id: number) => {
    if (!mutations) return
    mutations.deleteParty.mutate(id, {
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
                <Plus className="mr-1 size-3" /> 添加当事人
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>添加当事人</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium">客户ID</label>
                  <Input
                    type="number"
                    placeholder="请输入客户ID"
                    value={newClientId}
                    onChange={(e) => setNewClientId(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">诉讼地位</label>
                  <Select onValueChange={setNewLegalStatus} value={newLegalStatus}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="选择诉讼地位" />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(LEGAL_STATUS_LABELS).map(([v, l]) => (
                        <SelectItem key={v} value={v}>{l.zh}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <DialogFooter>
                <Button
                  onClick={handleAdd}
                  disabled={!newClientId || mutations?.createParty.isPending}
                >
                  {mutations?.createParty.isPending && <Loader2 className="mr-1 size-3 animate-spin" />}
                  确认
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      )}

      {parties.length === 0 ? (
        <EmptyState />
      ) : (
        parties.map((party) => (
          <Card key={party.id} className="gap-0 py-0">
            <CardHeader className="py-4">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <Users className="text-muted-foreground size-4 shrink-0" />
                  <Link
                    to={generatePath.clientDetail(party.client)}
                    className="text-sm font-medium truncate hover:underline"
                  >
                    {party.client_detail?.name ?? '未知当事人'}
                  </Link>
                  <ExternalLink className="text-muted-foreground size-3 shrink-0" />
                </div>
                <div className="flex items-center gap-2">
                  {party.legal_status && (
                    <Badge variant="outline" className="shrink-0 text-xs">
                      {party.legal_status}
                    </Badge>
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
                          <AlertDialogTitle>确认删除</AlertDialogTitle>
                          <AlertDialogDescription>
                            确定要删除当事人「{party.client_detail?.name}」吗？
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>取消</AlertDialogCancel>
                          <AlertDialogAction variant="destructive" onClick={() => handleDelete(party.id)}>
                            删除
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  )}
                </div>
              </div>
            </CardHeader>
          </Card>
        ))
      )}
    </div>
  )
}

export default CasePartySection
