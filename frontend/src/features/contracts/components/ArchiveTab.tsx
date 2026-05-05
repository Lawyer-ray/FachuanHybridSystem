import { useState, useCallback, useRef } from 'react'
import {
  Check, Circle, Upload, Trash2, RefreshCw, Archive, FolderSync,
  GripVertical, FileCheck, Loader2, Scaling,
} from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { contractApi } from '../api'
import type { Contract, FinalizedMaterial, MaterialCategory } from '../types'
import { MATERIAL_CATEGORY_LABELS } from '../types'

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
  { code: 'ARCHIVE_DOC', name: '归档文书', required: true, category: 'archive_document' },
  { code: 'SUPERVISION', name: '监督卡', required: false, category: 'supervision_card' },
  { code: 'AUTH', name: '授权委托材料', required: true, category: 'authorization_material' },
]

function isItemDone(item: ChecklistItem, materials: FinalizedMaterial[]): boolean {
  return materials.some(m => m.category === item.category)
}

function DetailCard({ title, children, extra }: { title: string; children: React.ReactNode; extra?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border/60 p-[18px] mb-4 bg-card">
      <div className="flex items-center justify-between mb-3.5">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        {extra}
      </div>
      {children}
    </div>
  )
}

export function ArchiveTab({ contract: c }: { contract: Contract }) {
  const [materials, setMaterials] = useState<FinalizedMaterial[]>(c.finalized_materials ?? [])
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [deleteMaterialId, setDeleteMaterialId] = useState<number | null>(null)
  const [confirmArchiveOpen, setConfirmArchiveOpen] = useState(false)
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
    } catch {}
  }, [c.id])

  const handleUpload = useCallback(async (code: string, file: File) => {
    setActionLoading(`upload-${code}`)
    try {
      await contractApi.uploadArchiveItem(c.id, code, file)
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
      toast.success('已切换紧凑模式')
    } catch { toast.error('操作失败') }
    setActionLoading(null)
  }, [c.id])

  const handleScaleToA4 = useCallback(async () => {
    setActionLoading('scale')
    try {
      await contractApi.scaleToA4(c.id)
      toast.success('A4缩放完成')
    } catch { toast.error('操作失败') }
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

  const getMaterialsForCode = (code: string) => materials.filter(m => m.archive_item_code === code)

  return (
    <div>
      {/* Hidden file input */}
      <input ref={uploadInputRef} type="file" className="hidden" onChange={onFileSelected} />

      {/* Archive Actions Bar */}
      <DetailCard title="归档操作">
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline" size="sm" className="h-8 text-xs"
            onClick={handleSyncCaseMaterials}
            disabled={!!actionLoading}
          >
            {actionLoading === 'sync' ? <Loader2 className="mr-1.5 size-3.5 animate-spin" /> : <FolderSync className="mr-1.5 size-3.5" />}
            同步案件材料
          </Button>
          <Button
            variant="outline" size="sm" className="h-8 text-xs"
            onClick={handleScaleToA4}
            disabled={!!actionLoading}
          >
            {actionLoading === 'scale' ? <Loader2 className="mr-1.5 size-3.5 animate-spin" /> : <Scaling className="mr-1.5 size-3.5" />}
            缩放至A4
          </Button>
          <Button
            variant="outline" size="sm" className="h-8 text-xs"
            onClick={handleToggleCompact}
            disabled={!!actionLoading}
          >
            {actionLoading === 'compact' ? <Loader2 className="mr-1.5 size-3.5 animate-spin" /> : <RefreshCw className="mr-1.5 size-3.5" />}
            紧凑模式
          </Button>
          <Button
            size="sm" className="h-8 text-xs"
            onClick={() => setConfirmArchiveOpen(true)}
            disabled={!canArchive || !!actionLoading}
          >
            {actionLoading === 'confirm' ? <Loader2 className="mr-1.5 size-3.5 animate-spin" /> : <Archive className="mr-1.5 size-3.5" />}
            确认归档
          </Button>
          {!canArchive && (
            <span className="text-xs text-muted-foreground self-center ml-1">
              必选项未全部完成，无法归档
            </span>
          )}
        </div>
      </DetailCard>

      {/* Checklist */}
      <DetailCard
        title="归档检查清单"
        extra={
          <span className="text-muted-foreground text-xs">
            {doneCount}/{items.length} 完成 · 必选 {requiredDone}/{requiredItems.length}
          </span>
        }
      >
        <Progress value={pct} className="h-1.5 mb-4" />

        <div className="flex flex-col gap-1.5">
          {items.map(item => {
            const itemMaterials = getMaterialsForCode(item.code)
            return (
              <div key={item.code} className="rounded-md border border-border/60 bg-muted/30 overflow-hidden">
                {/* Checklist header */}
                <div className="flex items-center gap-3 px-3 py-2.5 text-[13px]">
                  {item.done ? (
                    <span className="flex size-5 items-center justify-center rounded-full bg-green-100 text-xs text-green-600 shrink-0"><Check className="size-3" /></span>
                  ) : (
                    <span className="flex size-5 items-center justify-center rounded-full border border-border text-xs text-muted-foreground shrink-0"><Circle className="size-3" /></span>
                  )}
                  <span className={`flex-1 ${item.required ? 'font-medium' : ''}`}>{item.name}</span>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium ${
                    item.required ? 'bg-amber-50 text-amber-700' : 'bg-muted text-muted-foreground'
                  }`}>
                    {item.required ? '必选' : '可选'}
                  </span>
                  <Button
                    variant="ghost" size="sm" className="h-6 text-[11px] px-2"
                    onClick={() => triggerUpload(item.code)}
                    disabled={!!actionLoading}
                  >
                    <Upload className="mr-1 size-3" />
                    上传
                  </Button>
                </div>

                {/* Materials under this item */}
                {itemMaterials.length > 0 && (
                  <div className="border-t border-border/40 px-3 py-2 space-y-1">
                    {itemMaterials.map(m => (
                      <div key={m.id} className="flex items-center gap-2 text-xs py-1 group">
                        <GripVertical className="size-3 text-muted-foreground/50 shrink-0" />
                        <FileCheck className="size-3 text-green-600 shrink-0" />
                        <span className="flex-1 truncate">{m.original_filename}</span>
                        {m.remark && <span className="text-muted-foreground shrink-0">{m.remark}</span>}
                        <span className="text-muted-foreground shrink-0">{m.uploaded_at?.slice(0, 10) || ''}</span>
                        <Button
                          variant="ghost" size="icon" className="size-6 opacity-0 group-hover:opacity-100 text-destructive"
                          onClick={() => setDeleteMaterialId(m.id)}
                        >
                          <Trash2 className="size-3" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </DetailCard>

      {/* All materials flat list */}
      <DetailCard
        title="全部归档材料"
        extra={materials.length > 0 ? <span className="text-muted-foreground text-xs">{materials.length} 份</span> : undefined}
      >
        {materials.length === 0 ? (
          <p className="text-muted-foreground text-[13px] py-6 text-center">暂无归档材料</p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {materials.map(m => (
              <div
                key={m.id}
                className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-2.5 text-[13px] group"
              >
                <span className="flex-1 truncate font-medium">{m.original_filename}</span>
                <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0">
                  {m.category_label || MATERIAL_CATEGORY_LABELS[m.category]}
                </Badge>
                {m.remark && <span className="text-muted-foreground text-xs shrink-0">{m.remark}</span>}
                <span className="text-muted-foreground text-xs shrink-0">{m.uploaded_at?.slice(0, 10) || ''}</span>
                <Button
                  variant="ghost" size="icon" className="size-6 opacity-0 group-hover:opacity-100 text-destructive shrink-0"
                  onClick={() => setDeleteMaterialId(m.id)}
                >
                  <Trash2 className="size-3" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </DetailCard>

      {/* Delete confirmation */}
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

      {/* Confirm archive dialog */}
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
    </div>
  )
}
