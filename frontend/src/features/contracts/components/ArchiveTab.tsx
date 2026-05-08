import { useState, useCallback, useRef, useEffect } from 'react'
import {
  Upload, Trash2, Archive, FolderSync,
  GripVertical, FileCheck, Loader2, Scaling, ArrowRightLeft,
  ChevronDown, ChevronRight, Download, Eye, FolderOpen, Sparkles,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  DndContext, closestCorners, KeyboardSensor, PointerSensor,
  useSensor, useSensors, type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext, useSortable, verticalListSortingStrategy,
  arrayMove, sortableKeyboardCoordinates,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { FolderScanPanel } from './FolderScanPanel'
import { contractApi } from '../api'
import type { Contract, ChecklistItem, ArchiveChecklist, FinalizedMaterial } from '../types'

/* ── Status badge per item ── */

function ItemBadge({ item }: { item: ChecklistItem }) {
  if (item.template) {
    return (
      <span className="inline-flex items-center justify-center size-5 rounded-full bg-blue-100 text-blue-700 text-[11px] font-bold" title="可自动生成">
        ⚡
      </span>
    )
  }
  if (item.completed) {
    return (
      <span className="inline-flex items-center justify-center size-5 rounded-full bg-green-100 text-green-700 text-[11px] font-bold" title="已完成">
        ✓
      </span>
    )
  }
  if (item.auto_detect === 'supervision_card') {
    return (
      <span className="inline-flex items-center justify-center size-5 rounded-full bg-violet-100 text-violet-700 text-[11px] font-bold cursor-help" title="可自动检测监督卡">
        🔍
      </span>
    )
  }
  if (item.has_case_material) {
    return (
      <span className="inline-flex items-center justify-center size-5 rounded-full bg-cyan-100 text-cyan-700 text-[11px] font-bold cursor-help" title="可从案件材料同步">
        📋
      </span>
    )
  }
  if (item.required) {
    return (
      <span className="inline-flex items-center justify-center size-5 rounded-full bg-amber-100 text-amber-700 text-[11px] font-bold" title="必需">
        !
      </span>
    )
  }
  return (
    <span className="inline-flex items-center justify-center size-5 rounded-full bg-muted text-muted-foreground text-[11px] font-bold" title="可选">
      -
    </span>
  )
}

/* ── Sortable material sub-item ── */

function SortableMaterialItem({
  m, contractId, itemCode, items, onDelete, onMove,
}: {
  m: FinalizedMaterial
  contractId: number
  itemCode: string
  items: ChecklistItem[]
  onDelete: (id: number) => void
  onMove: (id: number, targetCode: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: m.id,
    animateLayoutChanges: ({ isSorting, wasDragging }) => !isSorting && !wasDragging,
  })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : undefined,
    zIndex: isDragging ? 10 : undefined,
    position: 'relative' as const,
  }

  return (
    <div ref={setNodeRef} style={style} className="flex items-center gap-1.5 px-1.5 py-0.5 rounded text-xs group hover:bg-muted/40 transition-colors">
      <span className="text-muted-foreground/40 cursor-grab shrink-0" {...attributes} {...listeners}>
        <GripVertical className="size-3" />
      </span>
      <FileCheck className="size-3 text-green-600 shrink-0" />
      <span className="flex-1 truncate">{m.original_filename}</span>
      {m.source_label && (
        <span className={`inline-flex items-center px-1 py-px rounded text-[10px] font-medium shrink-0 ${
          m.source === 'case' ? 'bg-blue-50 text-blue-700'
          : m.source === 'scan' ? 'bg-purple-50 text-purple-700'
          : 'bg-muted text-muted-foreground'
        }`}>
          {m.source_label}
        </span>
      )}
      <button
        className="p-0.5 rounded text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-foreground transition-all"
        title="预览"
        onClick={() => contractApi.previewSingleMaterial(contractId, m.id)}
      >
        <Eye className="size-3" />
      </button>
      <div className="opacity-0 group-hover:opacity-100 shrink-0">
        <Select onValueChange={(targetCode) => onMove(m.id, targetCode)}>
          <SelectTrigger className="h-5 w-auto text-[10px] px-1 border-border/60">
            <ArrowRightLeft className="size-2.5 mr-0.5" />
            <SelectValue placeholder="移动" />
          </SelectTrigger>
          <SelectContent>
            {items.filter(i => i.code !== itemCode).map(target => (
              <SelectItem key={target.code} value={target.code} className="text-xs">{target.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <button
        className="p-0.5 rounded text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-destructive transition-all"
        title="删除"
        onClick={() => onDelete(m.id)}
      >
        <Trash2 className="size-3" />
      </button>
    </div>
  )
}

/* ── Main component ── */

export function ArchiveTab({ contract: c }: { contract: Contract }) {
  const [checklist, setChecklist] = useState<ArchiveChecklist | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [deleteMaterialId, setDeleteMaterialId] = useState<number | null>(null)
  const [confirmArchiveOpen, setConfirmArchiveOpen] = useState(false)
  const [confirmClearAllOpen, setConfirmClearAllOpen] = useState(false)
  const [folderScanOpen, setFolderScanOpen] = useState(false)
  const [expandedCodes, setExpandedCodes] = useState<Set<string>>(new Set())
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const [uploadTargetCode, setUploadTargetCode] = useState<string | null>(null)

  /* ── Placeholder preview state ── */
  const [placeholderPreview, setPlaceholderPreview] = useState<{
    open: boolean
    title: string
    loading: boolean
    rows: { key: string; label: string; value: string }[]
  }>({ open: false, title: '', loading: false, rows: [] })

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const fetchChecklist = useCallback(async () => {
    try {
      const data = await contractApi.getArchiveChecklist(c.id)
      setChecklist(data)
    } catch {
      toast.error('获取检查清单失败')
    }
  }, [c.id])

  useEffect(() => {
    fetchChecklist()
  }, [fetchChecklist])

  const items = checklist?.items ?? []
  const doneCount = checklist?.completed_count ?? 0
  const requiredDone = checklist?.required_completed_count ?? 0
  const requiredTotal = checklist?.required_total_count ?? 0
  const pct = checklist?.completion_percentage ?? 0
  const compactMode = checklist?.compact_archive ?? false
  const canArchive = requiredDone === requiredTotal && requiredTotal > 0

  const refreshChecklist = useCallback(async () => {
    try {
      const data = await contractApi.getArchiveChecklist(c.id)
      setChecklist(data)
    } catch { /* 保持当前数据 */ }
  }, [c.id])

  const toggleExpand = (code: string) => {
    setExpandedCodes(prev => {
      const next = new Set(prev)
      if (next.has(code)) next.delete(code)
      else next.add(code)
      return next
    })
  }

  const toggleAllExpand = () => {
    if (expandedCodes.size > 0) {
      setExpandedCodes(new Set())
    } else {
      setExpandedCodes(new Set(items.map(i => i.code)))
    }
  }

  const getMaterialsForCode = (code: string) => {
    const item = items.find(i => i.code === code)
    return item?.materials ?? []
  }

  /* ── Actions ── */

  const handleUpload = useCallback(async (code: string, file: File) => {
    setActionLoading(`upload-${code}`)
    try {
      await contractApi.uploadArchiveItem(c.id, file, code)
      toast.success('上传成功')
      await refreshChecklist()
    } catch { toast.error('上传失败') }
    setActionLoading(null)
  }, [c.id, refreshChecklist])

  const handleDeleteMaterial = useCallback(async () => {
    if (deleteMaterialId == null) return
    setActionLoading(`delete-${deleteMaterialId}`)
    try {
      await contractApi.deleteArchiveMaterial(c.id, deleteMaterialId)
      toast.success('已删除')
      await refreshChecklist()
    } catch { toast.error('删除失败') }
    setDeleteMaterialId(null)
    setActionLoading(null)
  }, [c.id, deleteMaterialId, refreshChecklist])

  const handleSyncCaseMaterials = useCallback(async () => {
    setActionLoading('sync')
    try {
      const result = await contractApi.syncCaseMaterials(c.id)
      toast.success(`同步完成，${result.synced_count} 个文件`)
      await refreshChecklist()
    } catch { toast.error('同步失败') }
    setActionLoading(null)
  }, [c.id, refreshChecklist])

  const handleConfirmArchive = useCallback(async () => {
    setActionLoading('confirm')
    try {
      await contractApi.confirmArchive(c.id)
      toast.success('归档确认成功')
    } catch { toast.error('归档确认失败') }
    setConfirmArchiveOpen(false)
    setActionLoading(null)
  }, [c.id])

  const handleToggleCompact = useCallback(async () => {
    setActionLoading('compact')
    try {
      await contractApi.toggleCompactArchive(c.id)
      await refreshChecklist()
      toast.success(compactMode ? '已切换完整视图' : '已切换精简视图')
    } catch { toast.error('操作失败') }
    setActionLoading(null)
  }, [c.id, compactMode, refreshChecklist])

  const handleScaleToA4 = useCallback(async () => {
    setActionLoading('scale')
    try {
      await contractApi.scaleToA4(c.id)
      toast.success('A4缩放完成')
    } catch { toast.error('操作失败') }
    setActionLoading(null)
  }, [c.id])

  const handleMoveMaterial = useCallback(async (materialId: number, targetCode: string) => {
    try {
      await contractApi.moveArchiveMaterial(c.id, materialId, targetCode)
      toast.success('已移动')
      await refreshChecklist()
    } catch { toast.error('移动失败') }
  }, [c.id, refreshChecklist])

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id || !checklist) return

    const activeId = Number(active.id)
    const overId = Number(over.id)

    // Find which checklist item these materials belong to
    for (const item of checklist.items) {
      const matIds = item.materials.map(m => m.id)
      const activeIdx = matIds.indexOf(activeId)
      const overIdx = matIds.indexOf(overId)
      if (activeIdx < 0 || overIdx < 0) continue

      // Optimistic update: immediately reorder local state
      const reordered = arrayMove(matIds, activeIdx, overIdx)
      const reorderedMaterials = arrayMove(item.materials, activeIdx, overIdx)
      setChecklist(prev => {
        if (!prev) return prev
        return {
          ...prev,
          items: prev.items.map(i =>
            i.code === item.code ? { ...i, materials: reorderedMaterials } : i,
          ),
        }
      })

      // Persist to backend
      try {
        await contractApi.reorderArchiveMaterials(c.id, { [item.code]: reordered })
      } catch {
        toast.error('排序失败')
        refreshChecklist()
      }
      return
    }
  }, [c.id, checklist, refreshChecklist])

  const handleClearAll = useCallback(async () => {
    setActionLoading('clear-all')
    try {
      const result = await contractApi.clearAllArchiveMaterials(c.id)
      toast.success(`已清空 ${result.deleted_count} 份材料`)
      await refreshChecklist()
    } catch { toast.error('清空失败') }
    setConfirmClearAllOpen(false)
    setActionLoading(null)
  }, [c.id, refreshChecklist])

  const handleGenerateFolder = useCallback(async () => {
    setActionLoading('generate')
    try {
      const result = await contractApi.generateArchiveFolder(c.id)
      if (result.success) {
        toast.success(`归档文件夹已生成${result.generated_docs.length > 0 ? `，${result.generated_docs.length} 份文书` : ''}`)
        await refreshChecklist()
      } else {
        toast.error(result.errors[0] || '生成失败')
      }
    } catch { toast.error('生成归档文件夹失败') }
    setActionLoading(null)
  }, [c.id, refreshChecklist])

  const handleLearnRules = useCallback(async () => {
    setActionLoading('learn')
    try {
      const result = await contractApi.learnArchiveRules()
      if (result.success) {
        toast.success(result.message)
      } else {
        toast.error(result.message || '学习失败')
      }
    } catch { toast.error('学习分类规则失败') }
    setActionLoading(null)
  }, [])

  const triggerUpload = (code: string) => {
    setUploadTargetCode(code)
    uploadInputRef.current?.click()
  }

  const onFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && uploadTargetCode) handleUpload(uploadTargetCode, file)
    e.target.value = ''
  }

  const handlePreviewPlaceholders = useCallback(async (templateSubtype: string, templateName: string) => {
    setPlaceholderPreview({ open: true, title: `${templateName} - 替换词预览`, loading: true, rows: [] })
    try {
      const result = await contractApi.previewArchivePlaceholders(c.id, templateSubtype)
      if (result.success && result.data) {
        setPlaceholderPreview(prev => ({ ...prev, loading: false, rows: result.data! }))
      } else {
        toast.error(result.error || '预览失败')
        setPlaceholderPreview(prev => ({ ...prev, open: false }))
      }
    } catch {
      toast.error('预览请求失败')
      setPlaceholderPreview(prev => ({ ...prev, open: false }))
    }
  }, [c.id])

  /* ── Non-template items for count calculation ── */

  const nonTemplateItems = items.filter(i => !i.template)

  /* ── Visible items: preserve API order, compact mode only hides empty optional non-template ── */

  const visibleItems = items.filter(i => i.template || !compactMode || i.completed || i.required)

  return (
    <div>
      {/* Hidden file input */}
      <input ref={uploadInputRef} type="file" className="hidden" onChange={onFileSelected} />

      {/* ── Archive Checklist ── */}
      <div className="rounded-lg border border-border/60 bg-card overflow-hidden">

        {/* Header */}
        <div className="px-[18px] pt-[18px] pb-3">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2.5">
              <h3 className="text-sm font-semibold text-foreground">归档检查清单</h3>
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-muted text-muted-foreground">
                {doneCount}/{nonTemplateItems.length}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button
                className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                title={expandedCodes.size > 0 ? '收起全部子项' : '展开全部子项'}
                onClick={toggleAllExpand}
              >
                {expandedCodes.size > 0
                  ? <ChevronDown className="size-4" />
                  : <ChevronRight className="size-4" />}
              </button>
              <button
                className={`p-1.5 rounded-md transition-colors ${compactMode ? 'text-primary bg-primary/10' : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'}`}
                title={compactMode ? '显示全部' : '精简视图'}
                onClick={handleToggleCompact}
                disabled={!!actionLoading}
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="2" width="12" height="12" rx="2" />
                  <line x1="2" y1="6" x2="14" y2="6" />
                  <line x1="2" y1="10" x2="14" y2="10" />
                </svg>
              </button>
              <button
                className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                title="清空全部材料"
                onClick={() => setConfirmClearAllOpen(true)}
                disabled={!!actionLoading || items.every(i => i.materials.length === 0)}
              >
                <Trash2 className="size-4" />
              </button>
            </div>
          </div>

          {/* Progress bar */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-primary/80 to-primary rounded-full transition-all duration-300"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground shrink-0">
              {doneCount}/{nonTemplateItems.length}
              {requiredDone < requiredTotal && (
                <span className="text-amber-600 ml-1">(必需项: {requiredDone}/{requiredTotal})</span>
              )}
            </span>
          </div>
        </div>

        {/* Toolbar */}
        <div className="px-[18px] pb-3 flex flex-wrap items-center gap-2 border-b border-border/40">
          <Button
            variant="outline" size="sm" className="h-7 text-xs"
            onClick={() => setFolderScanOpen(true)}
            disabled={!!actionLoading}
          >
            <FolderOpen className="mr-1 size-3" />
            从合同文件夹同步
          </Button>
          <Button
            variant="outline" size="sm" className="h-7 text-xs"
            onClick={handleGenerateFolder}
            disabled={!!actionLoading}
          >
            {actionLoading === 'generate' ? <Loader2 className="mr-1 size-3 animate-spin" /> : <FolderSync className="mr-1 size-3" />}
            生成归档文件夹
          </Button>
          <Button
            variant="outline" size="sm" className="h-7 text-xs"
            onClick={handleLearnRules}
            disabled={!!actionLoading}
          >
            {actionLoading === 'learn' ? <Loader2 className="mr-1 size-3 animate-spin" /> : <Sparkles className="mr-1 size-3" />}
            学习分类规则
          </Button>
          <Button
            variant="outline" size="sm" className="h-7 text-xs"
            onClick={handleSyncCaseMaterials}
            disabled={!!actionLoading}
          >
            {actionLoading === 'sync' ? <Loader2 className="mr-1 size-3 animate-spin" /> : <FolderSync className="mr-1 size-3" />}
            从案件材料同步
          </Button>
          <Button
            variant="outline" size="sm" className="h-7 text-xs"
            onClick={handleScaleToA4}
            disabled={!!actionLoading}
          >
            {actionLoading === 'scale' ? <Loader2 className="mr-1 size-3 animate-spin" /> : <Scaling className="mr-1 size-3" />}
            缩放至A4
          </Button>
          <div className="flex-1" />
          {canArchive && (
            <Button
              size="sm" className="h-7 text-xs"
              onClick={() => setConfirmArchiveOpen(true)}
              disabled={!!actionLoading}
            >
              {actionLoading === 'confirm' ? <Loader2 className="mr-1 size-3 animate-spin" /> : <Archive className="mr-1 size-3" />}
              确认归档
            </Button>
          )}
        </div>

        {/* Checklist items */}
        <div className="divide-y divide-border/40" style={{ counterReset: 'ac-counter' }}>
          {visibleItems.map((item, index) => {
            const itemMaterials = getMaterialsForCode(item.code)
            const isExpanded = expandedCodes.has(item.code)

            return (
              <div
                key={item.code}
                className={`transition-colors ${item.template ? 'bg-blue-50/40' : item.completed ? 'bg-green-50/30' : ''}`}
                style={{ counterIncrement: 'ac-counter' }}
              >
                {/* Item header */}
                <div
                  className="flex items-center gap-2.5 px-[18px] py-1.5 cursor-pointer hover:bg-muted/30 transition-colors select-none"
                  onClick={() => toggleExpand(item.code)}
                >
                  <span className="text-xs text-muted-foreground font-mono w-5 text-right shrink-0" style={{ content: 'counter(ac-counter)' }}>
                    {index + 1}.
                  </span>
                  <span className={`text-[13px] flex-1 ${item.required ? 'font-medium' : ''}`}>
                    {item.name}
                  </span>
                  {itemMaterials.length > 0 && (
                    <span className="text-xs text-muted-foreground">({itemMaterials.length})</span>
                  )}
                  <ItemBadge item={item} />

                  {/* Actions */}
                  <div className="flex items-center gap-0.5" onClick={e => e.stopPropagation()}>
                    {item.template ? (
                      <>
                        <button
                          className="p-1 rounded text-muted-foreground hover:text-blue-600 hover:bg-blue-50 transition-colors"
                          title="预览替换词"
                          onClick={() => handlePreviewPlaceholders(item.template!, item.name)}
                        >
                          <Eye className="size-3.5" />
                        </button>
                        <button
                          className="p-1 rounded text-muted-foreground hover:text-blue-600 hover:bg-blue-50 transition-colors"
                          title="下载材料"
                          onClick={() => contractApi.downloadArchiveItem(c.id, item.code)}
                        >
                          <Download className="size-3.5" />
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                          title="上传文件"
                          onClick={() => triggerUpload(item.code)}
                          disabled={!!actionLoading}
                        >
                          <Upload className="size-3.5" />
                        </button>
                        {item.completed && (
                          <>
                            <button
                              className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                              title="预览"
                              onClick={() => contractApi.previewArchiveItem(c.id, item.code)}
                            >
                              <Eye className="size-3.5" />
                            </button>
                            <button
                              className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                              title="下载材料"
                              onClick={() => contractApi.downloadArchiveItem(c.id, item.code)}
                            >
                              <Download className="size-3.5" />
                            </button>
                          </>
                        )}
                      </>
                    )}
                  </div>

                  {/* Expand indicator */}
                  <span className="text-muted-foreground shrink-0">
                    {isExpanded
                      ? <ChevronDown className="size-3.5" />
                      : <ChevronRight className="size-3.5" />}
                  </span>
                </div>

                {/* Materials sub-items */}
                {itemMaterials.length > 0 && (
                  <div
                    className="overflow-hidden transition-all duration-200"
                    style={{ maxHeight: isExpanded ? `${itemMaterials.length * 28 + 8}px` : '0px' }}
                  >
                    <div className="px-[18px] pb-1">
                      <DndContext sensors={sensors} collisionDetection={closestCorners} onDragEnd={handleDragEnd}>
                        <SortableContext items={itemMaterials.map(m => m.id)} strategy={verticalListSortingStrategy}>
                          {itemMaterials.map(m => (
                            <SortableMaterialItem
                              key={m.id}
                              m={m}
                              contractId={c.id}
                              itemCode={item.code}
                              items={items}
                              onDelete={setDeleteMaterialId}
                              onMove={handleMoveMaterial}
                            />
                          ))}
                        </SortableContext>
                      </DndContext>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Dialogs ── */}

      {/* Delete material */}
      <AlertDialog open={deleteMaterialId != null} onOpenChange={() => setDeleteMaterialId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除材料</AlertDialogTitle>
            <AlertDialogDescription>删除后无法恢复，文件将被永久移除。</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteMaterial} className="bg-destructive text-destructive-foreground">删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Confirm archive */}
      <AlertDialog open={confirmArchiveOpen} onOpenChange={setConfirmArchiveOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认归档</AlertDialogTitle>
            <AlertDialogDescription>
              确认归档后，合同状态将变为「已归档」，关联的案件将自动关闭。此操作不可逆。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmArchive}>确认归档</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Clear all materials */}
      <AlertDialog open={confirmClearAllOpen} onOpenChange={setConfirmClearAllOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认清空全部材料</AlertDialogTitle>
            <AlertDialogDescription>
              将删除所有 {items.reduce((sum, item) => sum + item.materials.length, 0)} 份归档材料，此操作不可逆。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleClearAll} className="bg-destructive text-destructive-foreground">清空全部</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Folder scan dialog */}
      <Dialog open={folderScanOpen} onOpenChange={setFolderScanOpen}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>从合同文件夹同步</DialogTitle>
          </DialogHeader>
          <FolderScanPanel contractId={c.id} />
        </DialogContent>
      </Dialog>

      {/* Placeholder preview dialog */}
      <Dialog open={placeholderPreview.open} onOpenChange={(open) => setPlaceholderPreview(prev => ({ ...prev, open }))}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{placeholderPreview.title}</DialogTitle>
          </DialogHeader>
          {placeholderPreview.loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="size-5 animate-spin text-muted-foreground" />
            </div>
          ) : placeholderPreview.rows.length > 0 ? (
            <div className="max-h-[60vh] overflow-y-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/60">
                    <th className="text-left py-2 pr-3 font-medium text-muted-foreground">占位符</th>
                    <th className="text-left py-2 font-medium text-muted-foreground">当前值</th>
                  </tr>
                </thead>
                <tbody>
                  {placeholderPreview.rows.map((row, i) => (
                    <tr key={i} className="border-b border-border/30">
                      <td className="py-1.5 pr-3 text-xs font-mono text-muted-foreground whitespace-nowrap">{row.label || row.key}</td>
                      <td className="py-1.5 text-[13px]">{row.value || <span className="text-muted-foreground italic">未填写</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">无替换词数据</p>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
