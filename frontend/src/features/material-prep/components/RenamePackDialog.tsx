import { useState } from 'react'
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
import { useRenamePack } from '../hooks/use-material-packs'
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
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <RenamePackDialogContent
        // 换包 / 重开时换 key 重建内容层，用 useState 初值回填标题。
        // 不能用 useEffect 回填：那会在打开的那一帧先渲染空值、再补一次渲染，
        // 用户看到的是输入框闪一下（且多一轮渲染）。
        // 'closed' 分支保证「关掉同一个包再打开」也重建——否则上次未保存的编辑会留在框里。
        key={open ? (pack?.id ?? 'x') : 'closed'}
        onOpenChange={onOpenChange}
        pack={pack}
      />
    </AlertDialog>
  )
}

/** 对话框内容层：输入态只在这里，挂载即带着当前标题 */
function RenamePackDialogContent({
  onOpenChange,
  pack,
}: {
  onOpenChange: (open: boolean) => void
  pack: InboxMessage | null
}) {
  const renamePack = useRenamePack()
  const renameSubject = useReader((s) => s.renameSubject)
  const [name, setName] = useState(pack?.subject ?? '')

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
  )
}
