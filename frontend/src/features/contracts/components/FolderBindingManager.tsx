import { useState, useCallback } from 'react'
import { Folder, Link, Unlink, FolderOpen, Cloud, HardDrive } from 'lucide-react'
import { toast } from 'sonner'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useFolderBinding } from '../hooks/use-folder-binding'
import { FolderBrowser } from './FolderBrowser'
import { FolderScanPanel } from './FolderScanPanel'
import { foldersApi } from '../api/folders'

const STORAGE_TYPES = [
  { value: 'local', label: '本地文件系统', icon: HardDrive },
  { value: 'webdav', label: '坚果云 WebDAV', icon: Cloud },
  { value: 'onedrive', label: 'OneDrive', icon: Cloud },
] as const

export function FolderBindingManager({ contractId }: { contractId: number }) {
  const { binding, createBinding, deleteBinding } = useFolderBinding(contractId)
  const [browserOpen, setBrowserOpen] = useState(false)
  const [storageType, setStorageType] = useState<string>('local')
  const [cloudAccountId, setCloudAccountId] = useState<number | null>(null)

  const { data: cloudAccounts } = useQuery({
    queryKey: ['cloud-storage-accounts'],
    queryFn: () => foldersApi.listCloudStorageAccounts(),
    staleTime: 5 * 60 * 1000,
  })

  const bd = binding.data

  const handleSelectFolder = useCallback(async (path: string) => {
    try {
      await createBinding.mutateAsync({
        folder_path: path,
        storage_type: storageType,
        storage_account_id: cloudAccountId,
      })
      toast.success('文件夹已绑定')
      setBrowserOpen(false)
    } catch { toast.error('绑定失败') }
  }, [createBinding, storageType, cloudAccountId])

  const handleUnbind = useCallback(async () => {
    try {
      await deleteBinding.mutateAsync()
      toast.success('已解除绑定')
    } catch { toast.error('解绑失败') }
  }, [deleteBinding])

  const handleOpenBind = () => {
    if (storageType !== 'local' && !cloudAccountId) {
      toast.error('请先选择云存储账号')
      return
    }
    setBrowserOpen(true)
  }

  const storageLabel = bd
    ? STORAGE_TYPES.find(t => t.value === (bd.storage_type || 'local'))?.label || '本地文件系统'
    : null

  const filteredAccounts = cloudAccounts?.filter(a => a.storage_type === storageType) ?? []

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle className="flex items-center gap-2 text-base"><Folder className="size-4" />文件夹绑定</CardTitle>
          <div className="flex items-center gap-2">
            <Select value={storageType} onValueChange={v => { setStorageType(v); setCloudAccountId(null) }}>
              <SelectTrigger className="w-[160px] h-8 text-xs">
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
                <SelectTrigger className="w-[180px] h-8 text-xs">
                  <SelectValue placeholder="选择账号" />
                </SelectTrigger>
                <SelectContent>
                  {filteredAccounts.map(a => (
                    <SelectItem key={a.id} value={String(a.id)}>{a.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
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
