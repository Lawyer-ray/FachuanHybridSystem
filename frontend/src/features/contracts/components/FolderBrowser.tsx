import { useState } from 'react'
import { Folder, ChevronRight, ArrowUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useFolderBrowse } from '../hooks/use-folder-binding'
import { useResizable } from '@/hooks/use-resizable'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (path: string) => void
  storageType?: string
  storageAccountId?: number
}

export function FolderBrowser({ open, onOpenChange, onSelect, storageType, storageAccountId }: Props) {
  const isCloud = Boolean(storageType && storageType !== 'local')
  const [currentPath, setCurrentPath] = useState<string | undefined>(isCloud ? '/' : undefined)
  const { data, isLoading } = useFolderBrowse(currentPath, storageType, storageAccountId)
  const { width, onResizeStart } = useResizable({ minWidth: 400, maxWidth: 1200, initialWidth: 512 })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-none"
        style={{ width }}
      >
        <DialogHeader>
          <DialogTitle>{isCloud ? '选择云存储文件夹' : '选择文件夹'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          {data?.path && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Folder className="size-4 shrink-0" />
              <span className="break-all">{data.path}</span>
            </div>
          )}
          {data?.parent_path && (
            <Button variant="ghost" size="sm" onClick={() => setCurrentPath(data.parent_path!)}>
              <ArrowUp className="mr-1 size-4" />上级目录
            </Button>
          )}
          <div className="max-h-[400px] overflow-y-auto rounded-md border">
            {isLoading ? (
              <div className="space-y-2 p-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
            ) : !data?.browsable ? (
              <p className="p-3 text-sm text-muted-foreground">{data?.message || '无法浏览'}</p>
            ) : data.entries.length === 0 ? (
              <p className="p-3 text-sm text-muted-foreground">空文件夹</p>
            ) : (
              data.entries.map(e => (
                <button key={e.path} type="button" className="flex w-full cursor-pointer items-center justify-between gap-3 border-b px-3 py-2 last:border-0 hover:bg-muted/50 text-left" onClick={() => setCurrentPath(e.path)}>
                  <div className="flex items-center gap-2 min-w-0">
                    <Folder className="size-4 shrink-0 text-amber-500" />
                    <span className="text-sm truncate">{e.name}</span>
                  </div>
                  <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                </button>
              ))
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button disabled={!data?.path} onClick={() => { if (data?.path) { onSelect(data.path); onOpenChange(false) } }}>选择此文件夹</Button>
        </DialogFooter>
        {/* 右边缘拖拽手柄 */}
        <div
          className="absolute top-0 right-0 h-full w-2 cursor-col-resize hover:bg-primary/10 transition-colors"
          onMouseDown={onResizeStart}
        />
      </DialogContent>
    </Dialog>
  )
}
