import { useState, useCallback } from 'react'
import { Folder, Link, Unlink, FolderOpen } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useFolderBinding } from '../hooks/use-folder-binding'
import { FolderBrowser } from './FolderBrowser'
import { FolderScanPanel } from './FolderScanPanel'

export function FolderBindingManager({ contractId }: { contractId: number }) {
  const { binding, createBinding, deleteBinding } = useFolderBinding(contractId)
  const [browserOpen, setBrowserOpen] = useState(false)

  const handleSelect = useCallback(async (path: string) => {
    try {
      await createBinding.mutateAsync(path)
      toast.success('文件夹已绑定')
    } catch { toast.error('绑定失败') }
  }, [createBinding])

  const handleUnbind = useCallback(async () => {
    try {
      await deleteBinding.mutateAsync()
      toast.success('已解除绑定')
    } catch { toast.error('解绑失败') }
  }, [deleteBinding])

  const bd = binding.data

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle className="flex items-center gap-2 text-base"><Folder className="size-4" />文件夹绑定</CardTitle>
          <Button size="sm" variant="outline" onClick={() => setBrowserOpen(true)}>
            <FolderOpen className="mr-1 size-4" />{bd ? '更换' : '绑定'}
          </Button>
        </CardHeader>
        <CardContent>
          {bd ? (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Link className="size-4 text-primary" />
                <span className="text-sm">{bd.folder_path_display}</span>
                <Badge variant={bd.is_accessible ? 'default' : 'destructive'} className="text-xs">
                  {bd.is_accessible ? '可访问' : '不可访问'}
                </Badge>
              </div>
              <Button variant="ghost" size="sm" className="text-destructive" onClick={handleUnbind}>
                <Unlink className="mr-1 size-4" />解绑
              </Button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">未绑定文件夹，点击"绑定"选择文件夹</p>
          )}
        </CardContent>
      </Card>

      {bd && <FolderScanPanel contractId={contractId} />}

      <FolderBrowser open={browserOpen} onOpenChange={setBrowserOpen} onSelect={handleSelect} />
    </div>
  )
}
