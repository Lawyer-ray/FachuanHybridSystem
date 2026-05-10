import { useState } from 'react'
import {
  FileText,
  Download,
  Link2,
  Unlink,
  Loader2,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { useTemplateMutations } from '../hooks/use-template-mutations'
import { useAvailableTemplates } from '../hooks/use-template-bindings'
import type {
  GenerateTemplateRequest,
  TemplateBinding,
  TemplateCategory,
  CaseParty,
} from '../types'
import { LEGAL_STATUS_LABELS } from '../types'

// ============================================================================
// Sub-components
// ============================================================================

function TemplateRow({
  binding,
  parties,
  caseId,
}: {
  binding: TemplateBinding
  parties: CaseParty[]
  caseId: number
}) {
  const mutations = useTemplateMutations(caseId)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [selectedClientId, setSelectedClientId] = useState<string>('')
  const [generateMode, setGenerateMode] = useState<'individual' | 'combined'>('individual')

  const handleGenerate = () => {
    const data: GenerateTemplateRequest = { template_id: binding.template_id }
    if (selectedClientId) {
      if (generateMode === 'combined') {
        data.client_ids = [parseInt(selectedClientId, 10)]
        data.mode = 'combined'
      } else {
        data.client_id = parseInt(selectedClientId, 10)
      }
    }
    mutations.generateTemplate.mutate(data, {
      onSuccess: (blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${binding.name}.docx`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        toast.success('文档已生成')
        setGenerateOpen(false)
      },
      onError: () => toast.error('生成失败'),
    })
  }

  const handleUnbind = () => {
    if (!binding.binding_id) return
    mutations.unbindTemplate.mutate(binding.binding_id, {
      onSuccess: () => toast.success('已解绑'),
      onError: () => toast.error('解绑失败'),
    })
  }

  return (
    <>
      <div className="group flex items-center gap-2 py-1.5">
        <FileText className="text-muted-foreground size-3.5 shrink-0" />
        <span className="text-[13px] font-medium truncate flex-1">{binding.name}</span>
        {binding.binding_source !== 'manual_bound' && (
          <span className="text-[11px] text-muted-foreground">{binding.binding_source_display}</span>
        )}
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <Button variant="ghost" size="icon-xs" onClick={() => setGenerateOpen(true)}>
            <Download className="size-3" />
          </Button>
          {binding.binding_id && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="icon-xs">
                  <Unlink className="text-muted-foreground size-3" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent size="sm">
                <AlertDialogHeader>
                  <AlertDialogTitle>确认解绑模板</AlertDialogTitle>
                  <AlertDialogDescription>确定要解绑「{binding.name}」吗？</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>取消</AlertDialogCancel>
                  <AlertDialogAction variant="destructive" onClick={handleUnbind}>解绑</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </div>

      <Dialog open={generateOpen} onOpenChange={setGenerateOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>生成文档 - {binding.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {parties.length > 0 && (
              <>
                <div className="space-y-2">
                  <label className="text-sm font-medium">选择当事人</label>
                  <Select value={selectedClientId} onValueChange={setSelectedClientId}>
                    <SelectTrigger><SelectValue placeholder="全部当事人" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">全部当事人</SelectItem>
                      {parties.map((p) => (
                        <SelectItem key={p.client} value={String(p.client)}>
                          {p.client_detail?.name ?? '未知'}
                          {p.legal_status && `（${LEGAL_STATUS_LABELS[p.legal_status as keyof typeof LEGAL_STATUS_LABELS]?.zh ?? p.legal_status}）`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {selectedClientId && (
                  <div className="space-y-2">
                    <label className="text-sm font-medium">生成模式</label>
                    <Select value={generateMode} onValueChange={(v) => setGenerateMode(v as 'individual' | 'combined')}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="individual">单独生成</SelectItem>
                        <SelectItem value="combined">合并生成</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGenerateOpen(false)}>取消</Button>
            <Button onClick={handleGenerate} disabled={mutations.generateTemplate.isPending}>
              {mutations.generateTemplate.isPending && <Loader2 className="mr-1 size-3 animate-spin" />}
              <Download className="mr-1 size-3" />
              生成文档
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function CategoryGroup({
  category,
  parties,
  caseId,
}: {
  category: TemplateCategory
  parties: CaseParty[]
  caseId: number
}) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div>
      <button
        type="button"
        className="flex items-center gap-1.5 w-full text-left py-1"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        <span className="text-xs font-medium text-muted-foreground">{category.category_display}</span>
        <span className="text-[11px] text-muted-foreground">({category.templates.length})</span>
      </button>

      {expanded && (
        <div className="pl-5 divide-y divide-border/40">
          {category.templates.map((t) => (
            <TemplateRow
              key={t.template_id}
              binding={t}
              parties={parties}
              caseId={caseId}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function BindTemplateDialog({
  open,
  onOpenChange,
  caseId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: number
}) {
  const { data: availableTemplates, isLoading } = useAvailableTemplates(caseId)
  const mutations = useTemplateMutations(caseId)
  const [selectedId, setSelectedId] = useState<string>('')

  const handleBind = () => {
    if (!selectedId) return
    mutations.bindTemplate.mutate(parseInt(selectedId, 10), {
      onSuccess: () => {
        toast.success('绑定成功')
        onOpenChange(false)
        setSelectedId('')
      },
      onError: () => toast.error('绑定失败'),
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>绑定模板</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          ) : !availableTemplates?.length ? (
            <p className="text-muted-foreground text-sm text-center py-4">没有可绑定的模板</p>
          ) : (
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {availableTemplates.map((t) => (
                <label
                  key={t.template_id}
                  className={`flex items-start gap-3 cursor-pointer p-3 rounded-md border transition-colors ${
                    selectedId === String(t.template_id) ? 'border-foreground bg-muted/50' : 'border-border hover:bg-muted/30'
                  }`}
                >
                  <input
                    type="radio"
                    name="template"
                    value={t.template_id}
                    checked={selectedId === String(t.template_id)}
                    onChange={(e) => setSelectedId(e.target.value)}
                    className="mt-0.5"
                  />
                  <div className="min-w-0">
                    <div className="text-sm font-medium">{t.name}</div>
                    {t.description && (
                      <div className="text-xs text-muted-foreground mt-0.5">{t.description}</div>
                    )}
                    {t.case_sub_type_display && (
                      <Badge variant="outline" className="text-xs mt-1">{t.case_sub_type_display}</Badge>
                    )}
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleBind} disabled={!selectedId || mutations.bindTemplate.isPending}>
            {mutations.bindTemplate.isPending && <Loader2 className="mr-1 size-3 animate-spin" />}
            绑定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export interface CaseTemplateSectionProps {
  categories: TemplateCategory[]
  parties: CaseParty[]
  caseId: number
}

export function CaseTemplateSection({ categories, parties, caseId }: CaseTemplateSectionProps) {
  const [bindOpen, setBindOpen] = useState(false)

  if (categories.length === 0) {
    return (
      <div>
        <p className="text-muted-foreground text-xs mb-2">暂无绑定模板</p>
        <Button size="xs" variant="ghost" className="h-5 px-1.5 text-[11px]" onClick={() => setBindOpen(true)}>
          <Link2 className="size-3 mr-0.5" /> 绑定模板
        </Button>
        <BindTemplateDialog open={bindOpen} onOpenChange={setBindOpen} caseId={caseId} />
      </div>
    )
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-muted-foreground">{categories.reduce((s, c) => s + c.templates.length, 0)} 个模板</span>
        <Button size="xs" variant="ghost" className="h-5 px-1.5 text-[11px]" onClick={() => setBindOpen(true)}>
          <Link2 className="size-3 mr-0.5" /> 绑定
        </Button>
      </div>

      {categories.map((cat) => (
        <CategoryGroup
          key={cat.category}
          category={cat}
          parties={parties}
          caseId={caseId}
        />
      ))}

      <BindTemplateDialog open={bindOpen} onOpenChange={setBindOpen} caseId={caseId} />
    </div>
  )
}

export default CaseTemplateSection
