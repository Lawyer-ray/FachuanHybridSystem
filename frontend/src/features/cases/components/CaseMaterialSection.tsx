import { useState, useMemo } from 'react'
import {
  Upload,
  Link2,
  Trash2,
  FileText,
  Loader2,
  ChevronDown,
  ChevronRight,
  ArrowUp,
  ArrowDown,
  FolderOpen,
} from 'lucide-react'
import { toast } from 'sonner'

import { Card, CardHeader } from '@/components/ui/card'
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

import { useMaterialMutations } from '../hooks/use-material-mutations'
import type {
  MaterialBindCandidate,
  MaterialBindItem,
  MaterialCategory,
  MaterialSide,
} from '../types'
import {
  MATERIAL_CATEGORY_LABELS,
  MATERIAL_SIDE_LABELS,
} from '../types'

// ============================================================================
// Types
// ============================================================================

interface MaterialGroup {
  key: string
  category: MaterialCategory
  side: MaterialSide | null
  typeName: string
  typeId: number | null
  items: MaterialBindCandidate[]
}

// ============================================================================
// Sub-components
// ============================================================================

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-8">
      <div className="bg-muted flex size-10 items-center justify-center rounded-full">
        <FolderOpen className="text-muted-foreground size-5" />
      </div>
      <p className="text-muted-foreground mt-3 text-sm">暂无材料数据</p>
    </div>
  )
}

function MaterialCard({
  item,
  onDelete,
  deletePending,
}: {
  item: MaterialBindCandidate
  onDelete: () => void
  deletePending: boolean
}) {
  const mat = item.material
  const sideLabel = mat?.side ? (MATERIAL_SIDE_LABELS[mat.side]?.zh ?? mat.side) : null

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <FileText className="text-muted-foreground size-4 shrink-0" />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium truncate">{item.file_name}</span>
                {mat && (
                  <Badge variant="secondary" className="shrink-0 text-xs">
                    {mat.type_name}
                  </Badge>
                )}
                {sideLabel && (
                  <Badge variant="outline" className="shrink-0 text-xs">{sideLabel}</Badge>
                )}
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {item.actor_name} · {new Date(item.uploaded_at).toLocaleDateString('zh-CN')}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {item.file_url && (
              <Button variant="ghost" size="icon-xs" asChild>
                <a href={item.file_url} target="_blank" rel="noopener noreferrer">
                  <FileText className="size-3" />
                </a>
              </Button>
            )}
            {mat && (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="ghost" size="icon-xs" disabled={deletePending}>
                    {deletePending ? <Loader2 className="size-3 animate-spin" /> : <Trash2 className="text-muted-foreground size-3" />}
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent size="sm">
                  <AlertDialogHeader>
                    <AlertDialogTitle>确认删除材料</AlertDialogTitle>
                    <AlertDialogDescription>
                      确定要删除「{item.file_name}」的材料绑定吗？附件文件不受影响。
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>取消</AlertDialogCancel>
                    <AlertDialogAction variant="destructive" onClick={onDelete}>
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
  )
}

function MaterialGroupCard({
  group,
  candidates,
  onMoveUp,
  onMoveDown,
  onDeleteAll,
  onBind,
  bindPending,
}: {
  group: MaterialGroup
  candidates: MaterialBindCandidate[]
  onMoveUp?: () => void
  onMoveDown?: () => void
  onDeleteAll: () => void
  onBind: (items: MaterialBindItem[]) => void
  bindPending: boolean
}) {
  const [expanded, setExpanded] = useState(true)
  const [showBind, setShowBind] = useState(false)
  const [selectedCandidates, setSelectedCandidates] = useState<Set<number>>(new Set())
  const sideLabel = group.side ? (MATERIAL_SIDE_LABELS[group.side]?.zh ?? group.side) : null

  const unbound = candidates.filter((c) => !c.material)

  const handleBind = () => {
    if (selectedCandidates.size === 0) return
    const items: MaterialBindItem[] = Array.from(selectedCandidates).map((attachmentId) => ({
      attachment_id: attachmentId,
      category: group.category,
      type_id: group.typeId,
      type_name: group.typeName,
      side: group.side,
    }))
    onBind(items)
    setSelectedCandidates(new Set())
    setShowBind(false)
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => setExpanded(!expanded)}>
          {expanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        </Button>
        <span className="text-sm font-medium">{group.typeName}</span>
        {sideLabel && <Badge variant="outline" className="text-xs">{sideLabel}</Badge>}
        <Badge variant="secondary" className="text-xs">{group.items.length} 项</Badge>
        <div className="flex-1" />
        {onMoveUp && (
          <Button variant="ghost" size="icon-xs" onClick={onMoveUp}>
            <ArrowUp className="size-3" />
          </Button>
        )}
        {onMoveDown && (
          <Button variant="ghost" size="icon-xs" onClick={onMoveDown}>
            <ArrowDown className="size-3" />
          </Button>
        )}
        <Button variant="ghost" size="icon-xs" onClick={() => setShowBind(true)}>
          <Link2 className="size-3" />
        </Button>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="ghost" size="icon-xs">
              <Trash2 className="text-muted-foreground size-3" />
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent size="sm">
            <AlertDialogHeader>
              <AlertDialogTitle>删除分组</AlertDialogTitle>
              <AlertDialogDescription>
                确定要删除「{group.typeName}」下的所有 {group.items.length} 项材料绑定吗？
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>取消</AlertDialogCancel>
              <AlertDialogAction variant="destructive" onClick={onDeleteAll}>
                删除全部
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      {expanded && (
        <div className="ml-6 space-y-1.5">
          {group.items.map((item) => (
            <MaterialCard
              key={item.attachment_id}
              item={item}
              onDelete={() => {}}
              deletePending={false}
            />
          ))}
        </div>
      )}

      {/* Bind dialog */}
      <Dialog open={showBind} onOpenChange={setShowBind}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>绑定附件到「{group.typeName}」</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2 max-h-[400px] overflow-y-auto">
            {unbound.length === 0 ? (
              <p className="text-muted-foreground text-sm text-center py-4">没有未绑定的附件</p>
            ) : (
              unbound.map((c) => (
                <label
                  key={c.attachment_id}
                  className="flex items-center gap-2 cursor-pointer p-2 rounded-md hover:bg-muted/50"
                >
                  <input
                    type="checkbox"
                    checked={selectedCandidates.has(c.attachment_id)}
                    onChange={(e) => {
                      const next = new Set(selectedCandidates)
                      if (e.target.checked) next.add(c.attachment_id)
                      else next.delete(c.attachment_id)
                      setSelectedCandidates(next)
                    }}
                    className="rounded"
                  />
                  <div className="min-w-0">
                    <div className="text-sm truncate">{c.file_name}</div>
                    <div className="text-xs text-muted-foreground">
                      {c.actor_name} · {new Date(c.uploaded_at).toLocaleDateString('zh-CN')}
                    </div>
                  </div>
                </label>
              ))
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowBind(false)}>取消</Button>
            <Button onClick={handleBind} disabled={selectedCandidates.size === 0 || bindPending}>
              {bindPending && <Loader2 className="mr-1 size-3 animate-spin" />}
              绑定 {selectedCandidates.size} 项
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export interface CaseMaterialSectionProps {
  candidates: MaterialBindCandidate[]
  caseId: number
}

export function CaseMaterialSection({ candidates, caseId }: CaseMaterialSectionProps) {
  const mutations = useMaterialMutations(caseId)
  const [uploading, setUploading] = useState(false)
  const [categoryFilter, setCategoryFilter] = useState<MaterialCategory | 'all'>('all')

  // Group materials by category + side + typeName
  const groups = useMemo((): MaterialGroup[] => {
    const map = new Map<string, MaterialGroup>()
    for (const c of candidates) {
      if (!c.material) continue
      const mat = c.material
      const key = `${mat.category}|${mat.side ?? ''}|${mat.type_name}`
      if (!map.has(key)) {
        map.set(key, {
          key,
          category: mat.category,
          side: mat.side,
          typeName: mat.type_name,
          typeId: mat.type_id,
          items: [],
        })
      }
      map.get(key)!.items.push(c)
    }
    const result = Array.from(map.values())
    if (categoryFilter !== 'all') {
      return result.filter((g) => g.category === categoryFilter)
    }
    return result
  }, [candidates, categoryFilter])

  const unboundCount = candidates.filter((c) => !c.material).length

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    setUploading(true)
    try {
      await mutations.uploadMaterials.mutateAsync(Array.from(files))
      toast.success(`已上传 ${files.length} 个文件`)
    } catch {
      toast.error('上传失败')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleBind = (items: MaterialBindItem[]) => {
    mutations.bindMaterials.mutate(items, {
      onSuccess: (res) => toast.success(`已绑定 ${res.saved_count} 项`),
      onError: () => toast.error('绑定失败'),
    })
  }

  return (
    <div className="space-y-4">
      {/* Header actions */}
      <div className="flex items-center gap-3 flex-wrap">
        <label>
          <input
            type="file"
            multiple
            className="hidden"
            onChange={handleUpload}
            accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.gif,.bmp,.tiff,.xls,.xlsx"
          />
          <Button size="sm" variant="outline" asChild>
            <span>
              {uploading ? <Loader2 className="mr-1 size-3 animate-spin" /> : <Upload className="mr-1 size-3" />}
              上传材料
            </span>
          </Button>
        </label>

        <Select value={categoryFilter} onValueChange={(v) => setCategoryFilter(v as MaterialCategory | 'all')}>
          <SelectTrigger className="w-[140px] h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部分类</SelectItem>
            {(Object.entries(MATERIAL_CATEGORY_LABELS) as [MaterialCategory, { zh: string }][]).map(([val, label]) => (
              <SelectItem key={val} value={val}>{label.zh}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {unboundCount > 0 && (
          <Badge variant="secondary" className="text-xs">
            {unboundCount} 个未绑定附件
          </Badge>
        )}
      </div>

      {/* Material groups */}
      {groups.length === 0 && candidates.length === 0 ? (
        <EmptyState />
      ) : groups.length === 0 ? (
        <div className="text-center py-8">
          <p className="text-muted-foreground text-sm">
            {categoryFilter !== 'all'
              ? `没有${MATERIAL_CATEGORY_LABELS[categoryFilter]?.zh ?? ''}数据`
              : '暂无已绑定材料'}
          </p>
          {unboundCount > 0 && (
            <p className="text-xs text-muted-foreground mt-1">
              有 {unboundCount} 个未绑定附件，请先绑定到材料类型
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {groups.map((group) => (
            <MaterialGroupCard
              key={group.key}
              group={group}
              candidates={candidates}
              onDeleteAll={() => {
                // Delete all materials in this group by category
                // This is a simplified approach - ideally we'd delete by group
                toast.info('批量删除功能开发中')
              }}
              onBind={handleBind}
              bindPending={mutations.bindMaterials.isPending}
            />
          ))}
        </div>
      )}

      {/* Unbound attachments section */}
      {unboundCount > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Link2 className="size-4 text-muted-foreground" />
            <span className="text-sm font-medium">未绑定附件</span>
            <Badge variant="secondary" className="text-xs">{unboundCount}</Badge>
          </div>
          <div className="ml-6 space-y-1.5">
            {candidates.filter((c) => !c.material).map((item) => (
              <Card key={item.attachment_id} className="gap-0 py-0">
                <CardHeader className="py-3">
                  <div className="flex items-center gap-2">
                    <FileText className="text-muted-foreground size-4 shrink-0" />
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">{item.file_name}</div>
                      <div className="text-xs text-muted-foreground">
                        {item.actor_name} · {new Date(item.uploaded_at).toLocaleDateString('zh-CN')}
                      </div>
                    </div>
                  </div>
                </CardHeader>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default CaseMaterialSection
