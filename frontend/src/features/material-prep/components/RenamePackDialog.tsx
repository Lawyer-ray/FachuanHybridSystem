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
import { useRenamePack } from '../hooks/use-inbox'
import { useReader } from '../store'
import type { InboxMessage } from '../types'

/** 重命名材料包标题：右键菜单 / 阅读器标题栏共用入口 */
export function RenamePackDialog({
  open,
  onOpenChange,
  pack,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  pack: InboxMessage | null
}) {
  const renamePack = useRenamePack()
  const renameSubject = useReader((s) => s.renameSubject)
  const [name, setName] = useState('')

  useEffect(() => {
    if (open) setName(pack?.subject ?? '')
  }, [open, pack])

  const canSave = name.trim().length > 0

  const submit = () => {
    if (!pack || !canSave) return
    const subject = name.trim()
    renamePack
      .mutateAsync({ id: pack.id, subject })
      .then(() => {
        renameSubject(pack.id, subject) // 同步已打开的阅读器标题
        onOpenChange(false)
        toast.success('已重命名')
      })
      .catch(() => toast.error('重命名失败，请重试'))
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>重命名材料包</AlertDialogTitle>
          <AlertDialogDescription>给材料包起个更清晰的名字，方便后续查找。</AlertDialogDescription>
        </AlertDialogHeader>
        <div className="py-3">
          <Input
            value={name}
            autoFocus
            maxLength={512}
            placeholder="材料包名称"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && canSave) submit()
            }}
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction disabled={!canSave || renamePack.isPending} onClick={submit}>
            {renamePack.isPending ? '保存中…' : '保存'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
