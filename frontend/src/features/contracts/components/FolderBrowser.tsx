import { useState } from 'react'
import { Folder, ChevronRight, ArrowUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useFolderBrowse } from '../hooks/use-folder-binding'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (path: string) => void
}

export function FolderBrowser({ open, onOpenChange, onSelect }: Props) {
  const [currentPath, setCurrentPath] = useState<string | undefined>()
  const { data, isLoading } = useFolderBrowse(currentPath)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>选择文件夹</DialogTitle></DialogHeader>
        <div className="space-y-2">
          {data?.path && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Folder className="size-4" />
              <span className="truncate">{data.path}</span>
            </div>
          )}
          {data?.parent_path && (
            <Button variant="ghost" size="sm" onClick={() => setCurrentPath(data.parent_path!)}>
              <ArrowUp className="mr-1 size-4" />上级目录
            </Button>
          )}
          <div className="max-h-[300px] overflow-y-auto rounded-md border">
            {isLoading ? (
              <div className="space-y-2 p-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
            ) : !data?.browsable ? (
              <p className="p-3 text-sm text-muted-foreground">{data?.message || '无法浏览'}</p>
            ) : data.entries.length === 0 ? (
              <p className="p-3 text-sm text-muted-foreground">空文件夹</p>
            ) : (
              data.entries.map(e => (
                <div key={e.path} className="flex cursor-pointer items-center justify-between border-b px-3 py-2 last:border-0 hover:bg-muted/50" onClick={() => setCurrentPath(e.path)}>
                  <div className="flex items-center gap-2">
                    <Folder className="size-4 text-amber-500" />
                    <span className="text-sm">{e.name}</span>
                  </div>
                  <ChevronRight className="size-4 text-muted-foreground" />
                </div>
              ))
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button disabled={!data?.path} onClick={() => { if (data?.path) { onSelect(data.path); onOpenChange(false) } }}>选择此文件夹</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
