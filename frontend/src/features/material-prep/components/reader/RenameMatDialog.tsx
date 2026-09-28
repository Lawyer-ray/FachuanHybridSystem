import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Input } from '@/components/ui/input'
import { useReader } from '../../store'

/** 重命名源文件（阅读器左栏）：只改 draft 里的展示名，随防抖保存落盘 */
export function RenameMatDialog({
  target,
  onClose,
}: {
  /** {mi, initial} = 待重命名的材料下标与当前名；null = 关闭 */
  target: { mi: number; initial: string } | null
  onClose: () => void
}) {
  const renameMatInDraft = useReader((s) => s.renameMatInDraft)
  const [name, setName] = useState('')

  useEffect(() => {
    if (target) setName(target.initial)
  }, [target])

  const canSave = !!target && name.trim().length > 0

  const submit = () => {
    if (!target || !canSave) return
    renameMatInDraft(target.mi, name.trim())
    onClose()
    toast.success('已重命名')
  }

  return (
    <AlertDialog open={!!target} onOpenChange={(o) => !o && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>重命名源文件</AlertDialogTitle>
          <AlertDialogDescription>只影响本材料包里的显示名，不改原始文件。</AlertDialogDescription>
        </AlertDialogHeader>
        <div className="py-3">
          <Input
            value={name}
            autoFocus
            maxLength={512}
            placeholder="源文件名"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && canSave) submit()
            }}
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction disabled={!canSave} onClick={submit}>
            保存
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
