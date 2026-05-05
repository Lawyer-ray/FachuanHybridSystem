import { useState } from 'react'
import {
  FolderOpen,
  Link2,
  Unlink,
  Loader2,
  Search,
} from 'lucide-react'
import { toast } from 'sonner'

import { Card, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'

import { useFolderMutations } from '../hooks/use-folder-mutations'
import type { FolderBinding, FolderScanCandidate, FolderScanSession } from '../types'

// ============================================================================
// Sub-components
// ============================================================================

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-8">
      <div className="bg-muted flex size-10 items-center justify-center rounded-full">
        <FolderOpen className="text-muted-foreground size-5" />
      </div>
      <p className="text-muted-foreground mt-3 text-sm">未绑定文件夹</p>
      <p className="text-muted-foreground text-xs mt-1">绑定文件夹后可扫描导入材料</p>
    </div>
  )
}

function BindingCard({
  binding,
  onDelete,
  deletePending,
}: {
  binding: FolderBinding
  onDelete: () => void
  deletePending: boolean
}) {
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <FolderOpen className="text-muted-foreground size-4 shrink-0" />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium truncate">{binding.folder_path_display || binding.folder_path}</span>
                {binding.is_accessible ? (
                  <Badge variant="secondary" className="shrink-0 text-xs text-green-700 bg-green-50">可访问</Badge>
                ) : (
                  <Badge variant="secondary" className="shrink-0 text-xs text-destructive bg-destructive/10">不可访问</Badge>
                )}
              </div>
              {binding.relative_path && (
                <div className="text-xs text-muted-foreground mt-0.5">
                  相对路径: {binding.relative_path}
                </div>
              )}
            </div>
          </div>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="icon-xs" disabled={deletePending}>
                {deletePending ? <Loader2 className="size-3 animate-spin" /> : <Unlink className="text-muted-foreground size-3" />}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent size="sm">
              <AlertDialogHeader>
                <AlertDialogTitle>确认解绑文件夹</AlertDialogTitle>
                <AlertDialogDescription>
                  确定要解绑文件夹「{binding.folder_path_display || binding.folder_path}」吗？
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>取消</AlertDialogCancel>
                <AlertDialogAction variant="destructive" onClick={onDelete}>
                  解绑
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </CardHeader>
    </Card>
  )
}

function ScanResultCard({
  candidate,
  selected,
  onToggle,
}: {
  candidate: FolderScanCandidate
  selected: boolean
  onToggle: () => void
}) {
  const confidenceColor = candidate.confidence >= 0.8 ? 'text-green-700' : candidate.confidence >= 0.5 ? 'text-amber-700' : 'text-destructive'

  return (
    <div
      className={`flex items-start gap-3 p-3 rounded-md border cursor-pointer transition-colors ${
        selected ? 'border-foreground bg-muted/50' : 'border-border hover:bg-muted/30'
      }`}
      onClick={onToggle}
    >
      <Checkbox checked={selected} onCheckedChange={onToggle} className="mt-0.5" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate">{candidate.filename}</span>
          <Badge variant="outline" className="text-xs shrink-0">{candidate.suggested_category === 'party' ? '当事人材料' : '非当事人材料'}</Badge>
        </div>
        <div className="text-xs text-muted-foreground mt-0.5">
          类型: {candidate.type_name_hint}
          {candidate.suggested_side && ` · ${candidate.suggested_side === 'our' ? '我方' : '对方'}`}
        </div>
        <div className="text-xs mt-0.5">
          置信度: <span className={confidenceColor}>{Math.round(candidate.confidence * 100)}%</span>
          {candidate.file_size > 0 && ` · ${(candidate.file_size / 1024).toFixed(1)} KB`}
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export interface CaseFolderSectionProps {
  binding: FolderBinding | null | undefined
  caseId: number
}

export function CaseFolderSection({ binding, caseId }: CaseFolderSectionProps) {
  const mutations = useFolderMutations(caseId)
  const [bindOpen, setBindOpen] = useState(false)
  const [folderPath, setFolderPath] = useState('')
  const [scanSession, setScanSession] = useState<FolderScanSession | null>(null)
  const [selectedCandidates, setSelectedCandidates] = useState<Set<number>>(new Set())
  const [scanning, setScanning] = useState(false)

  const handleBind = () => {
    if (!folderPath.trim()) return
    mutations.createFolderBinding.mutate(folderPath.trim(), {
      onSuccess: () => {
        toast.success('绑定成功')
        setBindOpen(false)
        setFolderPath('')
      },
      onError: () => toast.error('绑定失败'),
    })
  }

  const handleDelete = () => {
    mutations.deleteFolderBinding.mutate(undefined, {
      onSuccess: () => toast.success('已解绑'),
      onError: () => toast.error('解绑失败'),
    })
  }

  const handleScan = async () => {
    setScanning(true)
    try {
      const session = await mutations.startFolderScan.mutateAsync({})
      setScanSession(session)
      toast.success('扫描完成')
    } catch {
      toast.error('扫描失败')
    } finally {
      setScanning(false)
    }
  }

  const handleStage = () => {
    if (!scanSession || selectedCandidates.size === 0) return
    const items = scanSession.candidates.filter((_, i) => selectedCandidates.has(i))
    mutations.stageScanResults.mutate(
      { sessionId: scanSession.session_id, items },
      {
        onSuccess: (res) => {
          toast.success(`已导入 ${res.staged_count} 个文件`)
          setScanSession(null)
          setSelectedCandidates(new Set())
        },
        onError: () => toast.error('导入失败'),
      },
    )
  }

  const toggleCandidate = (index: number) => {
    const next = new Set(selectedCandidates)
    if (next.has(index)) next.delete(index)
    else next.add(index)
    setSelectedCandidates(next)
  }

  return (
    <div className="space-y-4">
      {/* Header actions */}
      <div className="flex items-center gap-3">
        {!binding && (
          <Button size="sm" variant="outline" onClick={() => setBindOpen(true)}>
            <Link2 className="mr-1 size-3" /> 绑定文件夹
          </Button>
        )}
        {binding && (
          <Button size="sm" variant="outline" onClick={handleScan} disabled={scanning}>
            {scanning ? <Loader2 className="mr-1 size-3 animate-spin" /> : <Search className="mr-1 size-3" />}
            扫描文件夹
          </Button>
        )}
      </div>

      {/* Binding info */}
      {!binding ? (
        <EmptyState />
      ) : (
        <BindingCard
          binding={binding}
          onDelete={handleDelete}
          deletePending={mutations.deleteFolderBinding.isPending}
        />
      )}

      {/* Scan progress */}
      {scanning && (
        <div className="space-y-2">
          <Progress value={undefined} className="h-2" />
          <p className="text-xs text-muted-foreground text-center">正在扫描文件夹...</p>
        </div>
      )}

      {/* Scan results */}
      {scanSession && scanSession.candidates.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">扫描结果</span>
              <Badge variant="secondary" className="text-xs">{scanSession.candidates.length} 个文件</Badge>
              {selectedCandidates.size > 0 && (
                <Badge variant="outline" className="text-xs">已选 {selectedCandidates.size}</Badge>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  const all = new Set(scanSession.candidates.map((_, i) => i))
                  setSelectedCandidates(all.size === selectedCandidates.size ? new Set() : all)
                }}
              >
                {selectedCandidates.size === scanSession.candidates.length ? '取消全选' : '全选'}
              </Button>
              <Button
                size="sm"
                onClick={handleStage}
                disabled={selectedCandidates.size === 0 || mutations.stageScanResults.isPending}
              >
                {mutations.stageScanResults.isPending && <Loader2 className="mr-1 size-3 animate-spin" />}
                导入选中文件
              </Button>
            </div>
          </div>

          <div className="space-y-1.5 max-h-[400px] overflow-y-auto">
            {scanSession.candidates.map((candidate, index) => (
              <ScanResultCard
                key={candidate.source_path}
                candidate={candidate}
                selected={selectedCandidates.has(index)}
                onToggle={() => toggleCandidate(index)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Bind dialog */}
      <Dialog open={bindOpen} onOpenChange={setBindOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>绑定文件夹</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>文件夹路径</Label>
              <Input
                placeholder="/path/to/case/folder"
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                输入案件文件夹的绝对路径，绑定后可扫描导入材料
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBindOpen(false)}>取消</Button>
            <Button onClick={handleBind} disabled={!folderPath.trim() || mutations.createFolderBinding.isPending}>
              {mutations.createFolderBinding.isPending && <Loader2 className="mr-1 size-3 animate-spin" />}
              绑定
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default CaseFolderSection
