import { useState, useCallback } from 'react'
import { Folder, Link, Unlink, FolderOpen, Cloud, HardDrive } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { useFolderBinding } from '../hooks/use-folder-binding'
import { FolderBrowser } from './FolderBrowser'
import { FolderScanPanel } from './FolderScanPanel'

const STORAGE_TYPES = [
  { value: 'local', label: '本地文件系统', icon: HardDrive },
  { value: 'webdav', label: '坚果云 WebDAV', icon: Cloud },
  { value: 'onedrive', label: 'OneDrive', icon: Cloud },
] as const

export function FolderBindingManager({ contractId }: { contractId: number }) {
  const { binding, createBinding, deleteBinding } = useFolderBinding(contractId)
  const [browserOpen, setBrowserOpen] = useState(false)
  const [bindDialogOpen, setBindDialogOpen] = useState(false)
  const [storageType, setStorageType] = useState<string>('local')
  const [cloudPath, setCloudPath] = useState('')
  const [cloudAccountId, setCloudAccountId] = useState<number | null>(null)

  const bd = binding.data

  const handleSelectLocal = useCallback(async (path: string) => {
    try {
      await createBinding.mutateAsync({ folder_path: path, storage_type: 'local' })
      toast.success('文件夹已绑定')
      setBrowserOpen(false)
    } catch { toast.error('绑定失败') }
  }, [createBinding])

  const handleCloudBind = useCallback(async () => {
    if (!cloudPath.trim()) {
      toast.error('请输入文件夹路径')
      return
    }
    try {
      await createBinding.mutateAsync({
        folder_path: cloudPath.trim(),
        storage_type: storageType,
        storage_account_id: cloudAccountId,
      })
      toast.success('文件夹已绑定')
      setBindDialogOpen(false)
      setCloudPath('')
    } catch { toast.error('绑定失败') }
  }, [createBinding, cloudPath, storageType, cloudAccountId])

  const handleUnbind = useCallback(async () => {
    try {
      await deleteBinding.mutateAsync()
      toast.success('已解除绑定')
    } catch { toast.error('解绑失败') }
  }, [deleteBinding])

  const handleOpenBind = () => {
    if (storageType === 'local') {
      setBrowserOpen(true)
    } else {
      setBindDialogOpen(true)
    }
  }

  const storageLabel = bd
    ? STORAGE_TYPES.find(t => t.value === (bd.storage_type || 'local'))?.label || '本地文件系统'
    : null

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle className="flex items-center gap-2 text-base"><Folder className="size-4" />文件夹绑定</CardTitle>
          <div className="flex items-center gap-2">
            <Select value={storageType} onValueChange={setStorageType}>
              <SelectTrigger className="w-[160px] h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STORAGE_TYPES.map(t => (
                  <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button size="sm" variant="outline" onClick={handleOpenBind}>
              <FolderOpen className="mr-1 size-4" />{bd ? '更换' : '绑定'}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {bd ? (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Link className="size-4 text-primary" />
                <span className="text-sm">{bd.folder_path_display}</span>
                {storageLabel && storageLabel !== '本地文件系统' && (
                  <Badge variant="secondary" className="text-xs">{storageLabel}</Badge>
                )}
                <Badge variant={bd.is_accessible ? 'default' : 'destructive'} className="text-xs">
                  {bd.is_accessible ? '可访问' : '不可访问'}
                </Badge>
              </div>
              <Button variant="ghost" size="sm" className="text-destructive" onClick={handleUnbind}>
                <Unlink className="mr-1 size-4" />解绑
              </Button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">未绑定文件夹，选择存储类型后点击"绑定"</p>
          )}
        </CardContent>
      </Card>

      {bd && <FolderScanPanel contractId={contractId} />}

      <FolderBrowser open={browserOpen} onOpenChange={setBrowserOpen} onSelect={handleSelectLocal} />

      {/* Cloud storage bind dialog */}
      <Dialog open={bindDialogOpen} onOpenChange={setBindDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>绑定云存储文件夹</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">文件夹路径</label>
              <Input
                placeholder="如：我的工作空间/合同/2026.01-某某案"
                value={cloudPath}
                onChange={e => setCloudPath(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                输入云存储中的相对路径（相对于存储根目录）
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBindDialogOpen(false)}>取消</Button>
            <Button onClick={handleCloudBind}>绑定</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
