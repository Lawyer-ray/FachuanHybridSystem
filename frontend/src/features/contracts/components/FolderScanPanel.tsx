import { useState, useCallback } from 'react'
import { Play, RefreshCw, Check, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useFolderScan, useScanStatus } from '../hooks/use-folder-scan'
import type { FolderScanCandidate } from '../types'

export function FolderScanPanel({ contractId }: { contractId: number }) {
  const { subfolders, startScan, confirmScan } = useFolderScan(contractId)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [subfolder, setSubfolder] = useState('')
  const [candidates, setCandidates] = useState<FolderScanCandidate[]>([])
  const { data: status } = useScanStatus(contractId, sessionId)

  const handleStart = useCallback(async (rescan = false) => {
    try {
      const res = await startScan.mutateAsync({ rescan, subfolder })
      setSessionId(res.session_id)
      toast.success('扫描已启动')
    } catch { toast.error('启动失败') }
  }, [startScan, subfolder])

  const handleConfirm = useCallback(async () => {
    if (!sessionId || !status?.candidates) return
    try {
      const items = (candidates.length > 0 ? candidates : status.candidates).map(c => ({
        source_path: c.source_path, selected: c.selected, category: c.suggested_category,
      }))
      const res = await confirmScan.mutateAsync({ sessionId, items })
      toast.success(`已导入 ${res.imported_count} 个文件`)
      setSessionId(null)
    } catch { toast.error('确认失败') }
  }, [sessionId, status, candidates, confirmScan])

  const toggleCandidate = (idx: number) => {
    const src = status?.candidates ?? []
    const list = candidates.length > 0 ? candidates : [...src]
    list[idx] = { ...list[idx], selected: !list[idx].selected }
    setCandidates(list)
  }

  const isRunning = status?.status === 'running' || status?.status === 'pending'
  const isDone = status?.status === 'completed'
  const displayCandidates = candidates.length > 0 ? candidates : status?.candidates ?? []

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">文件夹扫描</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          {(subfolders.data?.subfolders?.length ?? 0) > 0 && (
            <Select value={subfolder} onValueChange={setSubfolder}>
              <SelectTrigger className="w-[200px]"><SelectValue placeholder="选择子文件夹" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="">根目录</SelectItem>
                {subfolders.data?.subfolders.map(s => (
                  <SelectItem key={s.relative_path} value={s.relative_path}>{s.display_name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Button size="sm" onClick={() => handleStart(false)} disabled={isRunning || startScan.isPending}>
            <Play className="mr-1 size-4" />开始扫描
          </Button>
          <Button size="sm" variant="outline" onClick={() => handleStart(true)} disabled={isRunning || startScan.isPending}>
            <RefreshCw className="mr-1 size-4" />重新扫描
          </Button>
        </div>

        {isRunning && status && (
          <div className="space-y-2">
            <Progress value={status.progress} />
            <p className="text-xs text-muted-foreground">正在扫描: {status.current_file}</p>
          </div>
        )}

        {isDone && status && (
          <div className="space-y-3">
            <div className="flex gap-4 text-sm">
              <span>总文件: {status.summary.total_files}</span>
              <span>去重后: {status.summary.deduped_files}</span>
              <span>已分类: {status.summary.classified_files}</span>
            </div>
            {displayCandidates.length > 0 && (
              <div className="max-h-[300px] overflow-y-auto rounded-md border">
                {displayCandidates.map((c, i) => (
                  <div key={c.source_path} className="flex items-center justify-between border-b px-3 py-2 last:border-0">
                    <div className="flex items-center gap-2">
                      <Button variant="ghost" size="icon" className="size-6" onClick={() => toggleCandidate(i)}>
                        {c.selected ? <Check className="size-4 text-green-600" /> : <X className="size-4 text-muted-foreground" />}
                      </Button>
                      <div>
                        <p className="text-sm">{c.filename}</p>
                        <p className="text-xs text-muted-foreground">{c.suggested_category} · {(c.confidence * 100).toFixed(0)}%</p>
                      </div>
                    </div>
                    <Badge variant="outline" className="text-xs">{(c.file_size / 1024).toFixed(0)} KB</Badge>
                  </div>
                ))}
              </div>
            )}
            <Button onClick={handleConfirm} disabled={confirmScan.isPending}>
              {confirmScan.isPending ? '导入中...' : `确认导入 (${displayCandidates.filter(c => c.selected).length})`}
            </Button>
          </div>
        )}

        {status?.error_message && <p className="text-sm text-destructive">{status.error_message}</p>}
      </CardContent>
    </Card>
  )
}
