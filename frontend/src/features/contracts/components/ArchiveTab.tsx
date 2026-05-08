import { useState, useCallback, useRef } from 'react'
import {
  Upload, Trash2, Archive, FolderSync,
  GripVertical, FileCheck, Loader2, Scaling, ArrowRightLeft,
  ChevronDown, ChevronRight, Download, Eye,
} from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { contractApi } from '../api'
import type { Contract, FinalizedMaterial, MaterialCategory } from '../types'

/* ── Checklist definition ── */

interface ChecklistItem {
  code: string
  name: string
  required: boolean
  category: MaterialCategory
}

const CHECKLIST: ChecklistItem[] = [
  { code: 'CONTRACT', name: '合同正本', required: true, category: 'contract_original' },
  { code: 'SUPPLEMENT', name: '补充协议', required: false, category: 'supplementary_agreement' },
  { code: 'INVOICE', name: '发票', required: false, category: 'invoice' },
  { code: 'ARCHIVE_DOC', name: '归档文书', required: true, category: 'archive_doc' },
  { code: 'SUPERVISION', name: '监督卡', required: false, category: 'supervision_card' },
  { code: 'AUTH', name: '授权委托材料', required: true, category: 'auth_doc' },
]

function isItemDone(item: ChecklistItem, materials: FinalizedMaterial[]): boolean {
  return materials.some(m => m.category === item.category)
}

/* ── Status badge per item ── */

function ItemBadge({ item, materials }: { item: ChecklistItem; materials: FinalizedMaterial[] }) {
  const done = isItemDone(item, materials)
  if (done) {
    return (
      <span className="inline-flex items-center justify-center size-5 rounded-full bg-green-100 text-green-700 text-[11px] font-bold" title="已完成">
        ✓
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

/* ── Main component ── */

export function ArchiveTab({ contract: c }: { contract: Contract }) {
  const [materials, setMaterials] = useState<FinalizedMaterial[]>(c.finalized_materials ?? [])
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [deleteMaterialId, setDeleteMaterialId] = useState<number | null>(null)
  const [confirmArchiveOpen, setConfirmArchiveOpen] = useState(false)
  const [confirmClearAllOpen, setConfirmClearAllOpen] = useState(false)
  const [expandedCodes, setExpandedCodes] = useState<Set<string>>(new Set())
  const [compactMode, setCompactMode] = useState(false)
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const [uploadTargetCode, setUploadTargetCode] = useState<string | null>(null)

  const items = CHECKLIST.map(item => ({ ...item, done: isItemDone(item, materials) }))
  const doneCount = items.filter(i => i.done).length
  const requiredItems = items.filter(i => i.required)
  const requiredDone = requiredItems.filter(i => i.done).length
  const pct = items.length > 0 ? Math.round((doneCount / items.length) * 100) : 0
  const canArchive = requiredDone === requiredItems.length

  const refreshMaterials = useCallback(async () => {
    try {
      const updated = await contractApi.get(c.id)
      setMaterials(updated.finalized_materials ?? [])
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
      setExpandedCodes(new Set(CHECKLIST.map(c => c.code)))
    }
  }

  const getMaterialsForCode = (code: string) => materials.filter(m => m.archive_item_code === code)

  /* ── Actions ── */

  const handleUpload = useCallback(async (code: string, file: File) => {
    setActionLoading(`upload-${code}`)
    try {
      await contractApi.uploadArchiveItem(c.id, file, code)
      toast.success('上传成功')
      await refreshMaterials()
    } catch { toast.error('上传失败') }
    setActionLoading(null)
  }, [c.id, refreshMaterials])

  const handleDeleteMaterial = useCallback(async () => {
    if (deleteMaterialId == null) return
    setActionLoading(`delete-${deleteMaterialId}`)
    try {
      await contractApi.deleteArchiveMaterial(c.id, deleteMaterialId)
      toast.success('已删除')
      setMaterials(prev => prev.filter(m => m.id !== deleteMaterialId))
    } catch { toast.error('删除失败') }
    setDeleteMaterialId(null)
    setActionLoading(null)
  }, [c.id, deleteMaterialId])

  const handleSyncCaseMaterials = useCallback(async () => {
    setActionLoading('sync')
    try {
      const result = await contractApi.syncCaseMaterials(c.id)
      toast.success(`同步完成，${result.synced_count} 个文件`)
      await refreshMaterials()
    } catch { toast.error('同步失败') }
    setActionLoading(null)
  }, [c.id, refreshMaterials])

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
      setCompactMode(prev => !prev)
      toast.success(compactMode ? '已切换完整视图' : '已切换精简视图')
    } catch { toast.error('操作失败') }
    setActionLoading(null)
  }, [c.id, compactMode])

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
      await refreshMaterials()
    } catch { toast.error('移动失败') }
  }, [c.id, refreshMaterials])

  const handleClearAll = useCallback(async () => {
    setActionLoading('clear-all')
    try {
      const result = await contractApi.clearAllArchiveMaterials(c.id)
      toast.success(`已清空 ${result.deleted_count} 份材料`)
      setMaterials([])
    } catch { toast.error('清空失败') }
    setConfirmClearAllOpen(false)
    setActionLoading(null)
  }, [c.id])

  const triggerUpload = (code: string) => {
    setUploadTargetCode(code)
    uploadInputRef.current?.click()
  }

  const onFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && uploadTargetCode) handleUpload(uploadTargetCode, file)
    e.target.value = ''
  }

  /* ── Visible items (compact mode hides empty optional) ── */

  const visibleItems = compactMode
    ? items.filter(i => i.done || i.required)
    : items

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
                {doneCount}/{items.length}
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
                disabled={!!actionLoading || materials.length === 0}
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
              {doneCount}/{items.length}
              {requiredDone < requiredItems.length && (
                <span className="text-amber-600 ml-1">(必需项: {requiredDone}/{requiredItems.length})</span>
              )}
            </span>
          </div>
        </div>

        {/* Toolbar */}
        <div className="px-[18px] pb-3 flex flex-wrap items-center gap-2 border-b border-border/40">
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
          {visibleItems.map(item => {
            const itemMaterials = getMaterialsForCode(item.code)
            const isExpanded = expandedCodes.has(item.code)

            return (
              <div
                key={item.code}
                className={`transition-colors ${item.done ? 'bg-green-50/30' : ''}`}
                style={{ counterIncrement: 'ac-counter' }}
              >
                {/* Item header */}
                <div
                  className="flex items-center gap-3 px-[18px] py-2.5 cursor-pointer hover:bg-muted/30 transition-colors select-none"
                  onClick={() => toggleExpand(item.code)}
                >
                  <span className="text-xs text-muted-foreground font-mono w-5 text-right shrink-0" style={{ content: 'counter(ac-counter)' }}>
                    {CHECKLIST.indexOf(item) + 1}.
                  </span>
                  <span className={`text-[13px] flex-1 ${item.required ? 'font-medium' : ''}`}>
                    {item.name}
                  </span>
                  {itemMaterials.length > 0 && (
                    <span className="text-xs text-muted-foreground">({itemMaterials.length})</span>
                  )}
                  <ItemBadge item={item} materials={materials} />

                  {/* Actions */}
                  <div className="flex items-center gap-0.5" onClick={e => e.stopPropagation()}>
                    <button
                      className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                      title="上传文件"
                      onClick={() => triggerUpload(item.code)}
                      disabled={!!actionLoading}
                    >
                      <Upload className="size-3.5" />
                    </button>
                    {item.done && (
                      <>
                        <button
                          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                          title="预览"
                        >
                          <Eye className="size-3.5" />
                        </button>
                        <button
                          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                          title="下载材料"
                        >
                          <Download className="size-3.5" />
                        </button>
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
                    style={{ maxHeight: isExpanded ? `${itemMaterials.length * 40 + 16}px` : '0px' }}
                  >
                    <div className="px-[18px] pb-2 space-y-0.5">
                      {itemMaterials.map(m => (
                        <div
                          key={m.id}
                          className="flex items-center gap-2 px-2 py-1.5 rounded-md text-xs group hover:bg-muted/40 transition-colors"
                        >
                          <span className="text-muted-foreground/40 cursor-grab shrink-0" title="拖拽排序">
                            <GripVertical className="size-3" />
                          </span>
                          <FileCheck className="size-3 text-green-600 shrink-0" />
                          <span className="flex-1 truncate">{m.original_filename}</span>
                          {m.source_label && (
                            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 ${
                              m.source === 'case' ? 'bg-blue-50 text-blue-700'
                              : m.source === 'scan' ? 'bg-purple-50 text-purple-700'
                              : 'bg-muted text-muted-foreground'
                            }`}>
                              {m.source_label}
                            </span>
                          )}
                          {/* Move dropdown */}
                          <div className="opacity-0 group-hover:opacity-100 shrink-0">
                            <Select onValueChange={(targetCode) => handleMoveMaterial(m.id, targetCode)}>
                              <SelectTrigger className="h-6 w-auto text-[10px] px-1.5 border-border/60">
                                <ArrowRightLeft className="size-2.5 mr-0.5" />
                                <SelectValue placeholder="移动" />
                              </SelectTrigger>
                              <SelectContent>
                                {CHECKLIST.filter(c => c.code !== item.code).map(target => (
                                  <SelectItem key={target.code} value={target.code} className="text-xs">
                                    {target.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                          <button
                            className="p-0.5 rounded text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-destructive transition-all"
                            title="删除"
                            onClick={() => setDeleteMaterialId(m.id)}
                          >
                            <Trash2 className="size-3" />
                          </button>
                        </div>
                      ))}
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
              将删除所有 {materials.length} 份归档材料，此操作不可逆。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleClearAll} className="bg-destructive text-destructive-foreground">清空全部</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
