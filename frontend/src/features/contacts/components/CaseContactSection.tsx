/**
 * CaseContactSection - 案件工作人员联系方式区块（表格布局）
 */

import { useState } from 'react'
import { Users, Plus, Trash2, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'

import { useContactMutations } from '../hooks/use-contact-mutations'
import { CONTACT_ROLE_LABELS } from '../types'
import type { CaseContact, ContactRole } from '../types'
import { CASE_STAGE_LABELS } from '@/features/cases/types'
import type { CaseStage } from '@/features/cases/types'

export interface CaseContactSectionProps {
  contacts: CaseContact[]
  editable?: boolean
  caseId?: number
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-8">
      <div className="bg-muted flex size-10 items-center justify-center rounded-full">
        <Users className="text-muted-foreground size-5" />
      </div>
      <p className="text-muted-foreground mt-3 text-sm">暂无工作人员信息</p>
    </div>
  )
}

export function CaseContactSection({ contacts, editable, caseId }: CaseContactSectionProps) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [form, setForm] = useState({
    name: '',
    role: '' as ContactRole | '',
    phone: '',
    address: '',
    stage: '',
    authority_id: '',
    note: '',
  })

  const mutations = useContactMutations(caseId ?? 0)

  const resetForm = () => {
    setForm({ name: '', role: '', phone: '', address: '', stage: '', authority_id: '', note: '' })
  }

  const handleAdd = () => {
    if (!caseId || !form.name || !form.role) return
    mutations.createContact.mutate(
      {
        case_id: caseId,
        name: form.name,
        role: form.role as ContactRole,
        phone: form.phone || null,
        address: form.address || null,
        stage: form.stage || null,
        authority_id: form.authority_id ? Number(form.authority_id) : null,
        note: form.note || null,
      },
      {
        onSuccess: () => {
          toast.success('工作人员已添加')
          setDialogOpen(false)
          resetForm()
        },
        onError: () => toast.error('添加失败'),
      },
    )
  }

  const handleDelete = (id: number) => {
    mutations.deleteContact.mutate(id, {
      onSuccess: () => toast.success('已删除'),
      onError: () => toast.error('删除失败'),
    })
  }

  if (!contacts.length && !editable) {
    return <EmptyState />
  }

  return (
    <div className="space-y-3">
      {editable && caseId && (
        <div className="flex justify-end">
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline">
                <Plus className="size-4 mr-1" /> 添加工作人员
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>添加工作人员</DialogTitle>
              </DialogHeader>
              <div className="space-y-3 py-2">
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">姓名 *</label>
                  <Input
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="输入姓名"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">角色 *</label>
                  <Select value={form.role} onValueChange={(v) => setForm((f) => ({ ...f, role: v as ContactRole }))}>
                    <SelectTrigger><SelectValue placeholder="选择角色" /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(CONTACT_ROLE_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>{label.zh}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">阶段</label>
                  <Select value={form.stage} onValueChange={(v) => setForm((f) => ({ ...f, stage: v }))}>
                    <SelectTrigger><SelectValue placeholder="选择阶段（可选）" /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(CASE_STAGE_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>{label.zh}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">电话</label>
                  <Input
                    value={form.phone}
                    onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                    placeholder="联系电话"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">收件地址</label>
                  <Input
                    value={form.address}
                    onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
                    placeholder="邮寄送达地址"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">备注</label>
                  <Input
                    value={form.note}
                    onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
                    placeholder="如：派出法庭名称等"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => { setDialogOpen(false); resetForm() }}>取消</Button>
                <Button onClick={handleAdd} disabled={!form.name || !form.role || mutations.createContact.isPending}>
                  {mutations.createContact.isPending && <Loader2 className="size-4 mr-1 animate-spin" />}
                  保存
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      )}

      {contacts.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>姓名</TableHead>
                <TableHead>角色</TableHead>
                <TableHead>电话</TableHead>
                <TableHead>收件地址</TableHead>
                <TableHead>阶段</TableHead>
                <TableHead>主管机关</TableHead>
                <TableHead>备注</TableHead>
                {editable && caseId && <TableHead className="w-[60px]">操作</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {contacts.map((contact) => {
                const stageLabel = contact.stage
                  ? (CASE_STAGE_LABELS[contact.stage as CaseStage]?.zh ?? contact.stage)
                  : '-'
                return (
                  <TableRow key={contact.id}>
                    <TableCell className="font-medium">{contact.name}</TableCell>
                    <TableCell>{contact.role_display || contact.role}</TableCell>
                    <TableCell className="text-muted-foreground">{contact.phone || '-'}</TableCell>
                    <TableCell className="text-muted-foreground max-w-[200px] truncate">{contact.address || '-'}</TableCell>
                    <TableCell className="text-muted-foreground">{stageLabel}</TableCell>
                    <TableCell className="text-muted-foreground">{contact.authority_name || '-'}</TableCell>
                    <TableCell className="text-muted-foreground max-w-[150px] truncate">{contact.note || '-'}</TableCell>
                    {editable && caseId && (
                      <TableCell>
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button size="icon" variant="ghost" className="size-7">
                              <Trash2 className="size-3.5 text-destructive" />
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>确认删除</AlertDialogTitle>
                              <AlertDialogDescription>
                                确定要删除工作人员「{contact.name}」吗？此操作不可撤销。
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>取消</AlertDialogCancel>
                              <AlertDialogAction onClick={() => handleDelete(contact.id)}>
                                删除
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </TableCell>
                    )}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
