import { useState } from 'react'
import {
  FolderOpen,
  Link2,
  Unlink,
  Loader2,
  Search,
  Cloud,
  HardDrive,
} from 'lucide-react'
import { toast } from 'sonner'
import { useQuery } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
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

import { FolderBrowser } from '@/features/contracts/components/FolderBrowser'
import { materialsApi } from '../api/materials'
import { useFolderMutations } from '../hooks/use-folder-mutations'
import type { FolderBinding, FolderScanCandidate, FolderScanSession } from '../types'

const STORAGE_TYPES = [
  { value: 'local', label: '本地', icon: HardDrive },
  { value: 'webdav', label: '坚果云', icon: Cloud },
  { value: 'onedrive', label: 'OneDrive', icon: Cloud },
] as const

function ScanResultRow({
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
      className={`flex items-start gap-3 p-2 rounded-md border cursor-pointer transition-colors text-xs ${
        selected ? 'border-foreground bg-muted/50' : 'border-border hover:bg-muted/30'
      }`}
      onClick={onToggle}
    >
      <Checkbox checked={selected} onCheckedChange={onToggle} className="mt-0.5" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="font-medium truncate">{candidate.filename}</span>
          <Badge variant="outline" className="text-[10px] shrink-0 py-0">{candidate.suggested_category === 'party' ? '当事人材料' : '非当事人材料'}</Badge>
        </div>
        <div className="text-muted-foreground mt-0.5">
          {candidate.type_name_hint}
          {candidate.suggested_side && ` · ${candidate.suggested_side === 'our' ? '我方' : '对方'}`}
          {' · '}置信度: <span className={confidenceColor}>{Math.round(candidate.confidence * 100)}%</span>
          {candidate.file_size > 0 && ` · ${(candidate.file_size / 1024).toFixed(1)} KB`}
        </div>
      </div>
    </div>
  )
}

export interface CaseFolderSectionProps {
  binding: FolderBinding | null | undefined
  caseId: number
}

export function CaseFolderSection({ binding, caseId }: CaseFolderSectionProps) {
  const mutations = useFolderMutations(caseId)
  const [browserOpen, setBrowserOpen] = useState(false)
  const [storageType, setStorageType] = useState<string>('local')
  const [cloudAccountId, setCloudAccountId] = useState<number | null>(null)
  const [scanSession, setScanSession] = useState<FolderScanSession | null>(null)
  const [selectedCandidates, setSelectedCandidates] = useState<Set<number>>(new Set())
  const [scanning, setScanning] = useState(false)

  const { data: cloudAccounts } = useQuery({
    queryKey: ['case-cloud-storage-accounts'],
    queryFn: () => materialsApi.listCloudStorageAccounts(),
    staleTime: 5 * 60 * 1000,
  })

  const filteredAccounts = cloudAccounts?.filter(a => a.storage_type === storageType) ?? []

  const handleSelectFolder = (path: string) => {
    mutations.createFolderBinding.mutate(
      { folder_path: path, storage_type: storageType, storage_account_id: cloudAccountId },
      {
        onSuccess: () => {
          toast.success('绑定成功')
          setBrowserOpen(false)
        },
        onError: () => toast.error('绑定失败'),
      },
    )
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

  const handleOpenBind = () => {
    if (storageType !== 'local' && !cloudAccountId) {
      toast.error('请先选择云存储账号')
      return
    }
    setBrowserOpen(true)
  }

  const storageLabel = binding
    ? STORAGE_TYPES.find(t => t.value === (binding.storage_type || 'local'))?.label || '本地'
    : null

  return (
    <div className="space-y-3">
      {/* Binding row */}
      {!binding ? (
        <div className="flex items-center gap-2">
          <p className="text-muted-foreground text-xs">未绑定文件夹</p>
          <Select value={storageType} onValueChange={v => { setStorageType(v); setCloudAccountId(null) }}>
            <SelectTrigger className="w-[100px] h-6 text-[11px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STORAGE_TYPES.map(t => (
                <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {storageType !== 'local' && filteredAccounts.length > 0 && (
            <Select value={cloudAccountId ? String(cloudAccountId) : ''} onValueChange={v => setCloudAccountId(Number(v))}>
              <SelectTrigger className="w-[140px] h-6 text-[11px]">
                <SelectValue placeholder="选择账号" />
              </SelectTrigger>
              <SelectContent>
                {filteredAccounts.map(a => (
                  <SelectItem key={a.id} value={String(a.id)}>{a.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Button size="xs" variant="ghost" className="h-5 px-1.5 text-[11px]" onClick={handleOpenBind}>
            <Link2 className="size-3 mr-0.5" /> 绑定
          </Button>
        </div>
      ) : (
        <div className="group flex items-center gap-2 py-1.5">
          <FolderOpen className="text-muted-foreground size-3.5 shrink-0" />
          <span className="text-[13px] font-medium truncate flex-1">{binding.folder_path_display || binding.folder_path}</span>
          {storageLabel && storageLabel !== '本地' && (
            <Badge variant="secondary" className="text-[10px] shrink-0 py-0">{storageLabel}</Badge>
          )}
          {binding.is_accessible ? (
            <span className="text-[11px] text-green-700">可访问</span>
          ) : (
            <span className="text-[11px] text-destructive">不可访问</span>
          )}
          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <Button size="xs" variant="ghost" className="h-5 px-1.5 text-[11px]" onClick={handleScan} disabled={scanning}>
              {scanning ? <Loader2 className="size-3 animate-spin" /> : <Search className="size-3" />}
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="icon-xs">
                  <Unlink className="text-muted-foreground size-3" />
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
                  <AlertDialogAction variant="destructive" onClick={handleDelete}>解绑</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      )}

      {/* Relative path info */}
      {binding?.relative_path && (
        <p className="text-[11px] text-muted-foreground">相对路径: {binding.relative_path}</p>
      )}

      {/* Scan progress */}
      {scanning && (
        <div className="space-y-1.5">
          <Progress value={undefined} className="h-1.5" />
          <p className="text-[11px] text-muted-foreground text-center">正在扫描文件夹...</p>
        </div>
      )}

      {/* Scan results */}
      {scanSession && scanSession.candidates.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-medium">扫描结果</span>
              <span className="text-[11px] text-muted-foreground">{scanSession.candidates.length} 个文件</span>
              {selectedCandidates.size > 0 && (
                <span className="text-[11px] text-foreground">已选 {selectedCandidates.size}</span>
              )}
            </div>
            <div className="flex items-center gap-1">
              <Button
                size="xs"
                variant="ghost"
                className="h-5 px-1.5 text-[11px]"
                onClick={() => {
                  const all = new Set(scanSession.candidates.map((_, i) => i))
                  setSelectedCandidates(all.size === selectedCandidates.size ? new Set() : all)
                }}
              >
                {selectedCandidates.size === scanSession.candidates.length ? '取消全选' : '全选'}
              </Button>
              <Button
                size="xs"
                className="h-5 px-1.5 text-[11px]"
                onClick={handleStage}
                disabled={selectedCandidates.size === 0 || mutations.stageScanResults.isPending}
              >
                {mutations.stageScanResults.isPending && <Loader2 className="mr-0.5 size-3 animate-spin" />}
                导入
              </Button>
            </div>
          </div>

          <div className="space-y-1 max-h-[300px] overflow-y-auto">
            {scanSession.candidates.map((candidate, index) => (
              <ScanResultRow
                key={candidate.source_path}
                candidate={candidate}
                selected={selectedCandidates.has(index)}
                onToggle={() => toggleCandidate(index)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Folder browser (works for both local and cloud) */}
      <FolderBrowser
        open={browserOpen}
        onOpenChange={setBrowserOpen}
        onSelect={handleSelectFolder}
        storageType={storageType}
        storageAccountId={cloudAccountId ?? undefined}
      />
    </div>
  )
}

export default CaseFolderSection
