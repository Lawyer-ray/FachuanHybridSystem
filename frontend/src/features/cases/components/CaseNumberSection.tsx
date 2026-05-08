import { useState } from 'react'
import { Hash, Clock, Plus, Trash2, Loader2, ChevronDown, ChevronUp, Pencil, FileText, Scale } from 'lucide-react'
import { formatDateOnly } from '@/lib/date'
import { formatAmountInt } from '@/lib/format'
import { toast } from 'sonner'

import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

import { useCaseNumberMutations } from '../hooks/use-case-number-mutations'
import { type CaseNumber, YEAR_DAYS_CHOICES, DATE_INCLUSION_CHOICES } from '../types'

export interface CaseNumberSectionProps {
  caseNumbers: CaseNumber[]
  editable?: boolean
  caseId?: number
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

interface FormData {
  number: string
  document_name: string
  remarks: string
  is_active: boolean
  execution_cutoff_date: string
  execution_paid_amount: string
  execution_use_deduction_order: boolean
  execution_year_days: string
  execution_date_inclusion: string
  execution_manual_text: string
}

const EMPTY_FORM: FormData = {
  number: '',
  document_name: '',
  remarks: '',
  is_active: true,
  execution_cutoff_date: '',
  execution_paid_amount: '',
  execution_use_deduction_order: false,
  execution_year_days: '360',
  execution_date_inclusion: 'both',
  execution_manual_text: '',
}

function toForm(cn: CaseNumber): FormData {
  return {
    number: cn.number,
    document_name: cn.document_name ?? '',
    remarks: cn.remarks ?? '',
    is_active: cn.is_active,
    execution_cutoff_date: cn.execution_cutoff_date ?? '',
    execution_paid_amount: cn.execution_paid_amount?.toString() ?? '',
    execution_use_deduction_order: cn.execution_use_deduction_order,
    execution_year_days: cn.execution_year_days?.toString() ?? '360',
    execution_date_inclusion: cn.execution_date_inclusion ?? 'both',
    execution_manual_text: cn.execution_manual_text ?? '',
  } as FormData
}

function toPayload(form: FormData) {
  return {
    number: form.number.trim(),
    document_name: form.document_name.trim() || undefined,
    remarks: form.remarks.trim() || undefined,
    is_active: form.is_active,
    execution_cutoff_date: form.execution_cutoff_date || null,
    execution_paid_amount: form.execution_paid_amount ? parseFloat(form.execution_paid_amount) : 0,
    execution_use_deduction_order: form.execution_use_deduction_order,
    execution_year_days: form.execution_year_days ? parseInt(form.execution_year_days, 10) : null,
    execution_date_inclusion: form.execution_date_inclusion || null,
    execution_manual_text: form.execution_manual_text.trim() || null,
  }
}

function CaseNumberDialog({
  open, onOpenChange, form, setForm, onSubmit, submitLabel, loading,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  form: FormData
  setForm: React.Dispatch<React.SetStateAction<FormData>>
  onSubmit: () => void
  submitLabel: string
  loading: boolean
}) {
  const [showExecution, setShowExecution] = useState(false)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{submitLabel === '确认' ? '添加案号' : '编辑案号'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>案号 *</Label>
            <Input
              placeholder="如：(2025)京01民初123号"
              value={form.number}
              onChange={(e) => setForm(f => ({ ...f, number: e.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label>文书名称</Label>
            <Input
              placeholder="如：民事判决书、民事调解书"
              value={form.document_name}
              onChange={(e) => setForm(f => ({ ...f, document_name: e.target.value }))}
            />
          </div>
          <div className="flex items-center gap-3">
            <Switch
              checked={form.is_active}
              onCheckedChange={(checked) => setForm(f => ({ ...f, is_active: checked }))}
            />
            <Label className="text-sm font-normal">当前生效</Label>
          </div>
          <div className="space-y-2">
            <Label>备注</Label>
            <Input
              placeholder="备注（可选）"
              value={form.remarks}
              onChange={(e) => setForm(f => ({ ...f, remarks: e.target.value }))}
            />
          </div>

          {/* 执行参数折叠区 */}
          <Collapsible open={showExecution} onOpenChange={setShowExecution}>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="sm" className="w-full justify-between px-0 text-muted-foreground hover:text-foreground">
                <span className="flex items-center gap-1.5 text-xs font-medium">
                  <Scale className="size-3.5" />
                  执行请求参数
                </span>
                {showExecution ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-4 pt-3">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-xs">利息计算截止日</Label>
                  <Input
                    type="date"
                    value={form.execution_cutoff_date}
                    onChange={(e) => setForm(f => ({ ...f, execution_cutoff_date: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">已付金额</Label>
                  <Input
                    type="number"
                    placeholder="0"
                    value={form.execution_paid_amount}
                    onChange={(e) => setForm(f => ({ ...f, execution_paid_amount: e.target.value }))}
                  />
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-xs">年天数</Label>
                  <Select
                    value={form.execution_year_days}
                    onValueChange={(v) => setForm(f => ({ ...f, execution_year_days: v }))}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {YEAR_DAYS_CHOICES.map(opt => (
                        <SelectItem key={opt.value} value={String(opt.value)}>{opt.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">日期包含方式</Label>
                  <Select
                    value={form.execution_date_inclusion}
                    onValueChange={(v) => setForm(f => ({ ...f, execution_date_inclusion: v }))}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {DATE_INCLUSION_CHOICES.map(opt => (
                        <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Switch
                  checked={form.execution_use_deduction_order}
                  onCheckedChange={(checked) => setForm(f => ({ ...f, execution_use_deduction_order: checked }))}
                />
                <Label className="text-xs font-normal">使用扣减令</Label>
              </div>
              <div className="space-y-2">
                <Label className="text-xs">执行请求手动文本</Label>
                <textarea
                  className="border-input bg-background placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 w-full rounded-md border px-3 py-2 text-sm shadow-xs outline-none focus-visible:ring-[3px] min-h-[80px] resize-y"
                  placeholder="留空则自动生成"
                  value={form.execution_manual_text}
                  onChange={(e) => setForm(f => ({ ...f, execution_manual_text: e.target.value }))}
                />
              </div>
            </CollapsibleContent>
          </Collapsible>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={onSubmit} disabled={!form.number.trim() || loading}>
            {loading && <Loader2 className="mr-1 size-3 animate-spin" />}
            {submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function CaseNumberCard({
  cn, editable, caseId, mutations,
}: {
  cn: CaseNumber
  editable?: boolean
  caseId?: number
  mutations: ReturnType<typeof useCaseNumberMutations> | null
}) {
  const [expanded, setExpanded] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editForm, setEditForm] = useState<FormData>(() => toForm(cn))

  const handleEdit = () => {
    if (!mutations) return
    mutations.updateCaseNumber.mutate(
      { id: cn.id, data: toPayload(editForm) },
      {
        onSuccess: () => {
          toast.success('更新案号成功')
          setEditOpen(false)
        },
        onError: (e) => toast.error(e.message || '更新失败'),
      },
    )
  }

  const handleDelete = () => {
    if (!mutations) return
    mutations.deleteCaseNumber.mutate(cn.id, {
      onSuccess: () => toast.success('删除成功'),
      onError: (e) => toast.error(e.message || '删除失败'),
    })
  }

  const hasExecution = cn.execution_cutoff_date || cn.execution_paid_amount > 0 || cn.execution_manual_text

  return (
    <Card className="gap-0 py-0">
      <Collapsible open={expanded} onOpenChange={setExpanded}>
        <CardHeader className="pb-0 pt-4">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <Hash className="text-muted-foreground size-4 shrink-0" />
              <span className="text-sm font-medium truncate font-mono">{cn.number}</span>
              {cn.document_name && (
                <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0">
                  <FileText className="size-2.5 mr-0.5" />
                  {cn.document_name}
                </Badge>
              )}
              <Badge variant={cn.is_active ? 'default' : 'secondary'} className="text-[10px] px-1.5 py-0 shrink-0">
                {cn.is_active ? '生效' : '未生效'}
              </Badge>
            </div>
            <div className="flex items-center gap-1">
              <div className="flex items-center gap-1 text-muted-foreground shrink-0">
                <Clock className="size-3" />
                <span className="text-xs">{formatDateOnly(cn.created_at)}</span>
              </div>
              {hasExecution && (
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" size="icon-xs">
                    {expanded ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
                  </Button>
                </CollapsibleTrigger>
              )}
              {editable && caseId && (
                <>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    onClick={() => {
                      setEditForm(toForm(cn))
                      setEditOpen(true)
                    }}
                  >
                    <Pencil className="text-muted-foreground size-3" />
                  </Button>
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
                        <AlertDialogAction variant="destructive" onClick={handleDelete}>
                          删除
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </>
              )}
            </div>
          </div>
        </CardHeader>
        {cn.remarks && (
          <CardContent className="pb-2 pt-2">
            <p className="text-muted-foreground text-xs">{cn.remarks}</p>
          </CardContent>
        )}
        <CollapsibleContent>
          <CardContent className="pb-4 pt-2">
            <div className="rounded-md border border-border/60 bg-muted/30 px-3 py-2.5">
              <p className="text-xs font-medium text-muted-foreground mb-2">执行参数</p>
              <div className="grid gap-2 sm:grid-cols-2 text-[12px]">
                {cn.execution_cutoff_date && (
                  <div>
                    <span className="text-muted-foreground">利息截止日：</span>
                    <span className="font-medium">{formatDateOnly(cn.execution_cutoff_date)}</span>
                  </div>
                )}
                {cn.execution_paid_amount > 0 && (
                  <div>
                    <span className="text-muted-foreground">已付金额：</span>
                    <span className="font-medium">{formatAmountInt(cn.execution_paid_amount)}</span>
                  </div>
                )}
                {cn.execution_year_days != null && (
                  <div>
                    <span className="text-muted-foreground">年天数：</span>
                    <span className="font-medium">{cn.execution_year_days === 0 ? '按实际天数' : `${cn.execution_year_days}天`}</span>
                  </div>
                )}
                {cn.execution_date_inclusion && (
                  <div>
                    <span className="text-muted-foreground">日期包含：</span>
                    <span className="font-medium">
                      {DATE_INCLUSION_CHOICES.find(o => o.value === cn.execution_date_inclusion)?.label ?? cn.execution_date_inclusion}
                    </span>
                  </div>
                )}
                <div>
                  <span className="text-muted-foreground">扣减令：</span>
                  <span className="font-medium">{cn.execution_use_deduction_order ? '是' : '否'}</span>
                </div>
              </div>
              {cn.execution_manual_text && (
                <div className="mt-2 pt-2 border-t border-border/40">
                  <p className="text-xs text-muted-foreground mb-1">手动执行文本：</p>
                  <p className="text-[12px] whitespace-pre-wrap">{cn.execution_manual_text}</p>
                </div>
              )}
            </div>
          </CardContent>
        </CollapsibleContent>
      </Collapsible>

      {/* Edit Dialog */}
      {editable && caseId && (
        <CaseNumberDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          form={editForm}
          setForm={setEditForm}
          onSubmit={handleEdit}
          submitLabel="保存"
          loading={mutations?.updateCaseNumber.isPending ?? false}
        />
      )}
    </Card>
  )
}

export function CaseNumberSection({ caseNumbers, editable, caseId }: CaseNumberSectionProps) {
  const [addOpen, setAddOpen] = useState(false)
  const [addForm, setAddForm] = useState<FormData>(EMPTY_FORM)

  const mutations = useCaseNumberMutations(caseId ?? 0)

  const handleAdd = () => {
    if (!caseId) return
    mutations.createCaseNumber.mutate(
      { case_id: caseId, ...toPayload(addForm) },
      {
        onSuccess: () => {
          toast.success('添加案号成功')
          setAddOpen(false)
          setAddForm(EMPTY_FORM)
        },
        onError: (e) => toast.error(e.message || '添加失败'),
      },
    )
  }

  return (
    <div className="space-y-3">
      {editable && caseId && (
        <div className="flex justify-end">
          <Button size="sm" variant="outline" onClick={() => { setAddForm(EMPTY_FORM); setAddOpen(true) }}>
            <Plus className="mr-1 size-3" /> 添加案号
          </Button>
          <CaseNumberDialog
            open={addOpen}
            onOpenChange={setAddOpen}
            form={addForm}
            setForm={setAddForm}
            onSubmit={handleAdd}
            submitLabel="确认"
            loading={mutations?.createCaseNumber.isPending ?? false}
          />
        </div>
      )}

      {caseNumbers.length === 0 ? (
        <EmptyState />
      ) : (
        caseNumbers.map((cn) => (
          <CaseNumberCard
            key={cn.id}
            cn={cn}
            editable={editable}
            caseId={caseId}
            mutations={mutations}
          />
        ))
      )}
    </div>
  )
}

export default CaseNumberSection
