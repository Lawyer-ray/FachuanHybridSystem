import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { errMessage } from '@/lib/errors'

import { confirmProjectNote, type ProjectNote } from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'

/** 与后端 `write.NOTE_MAX_CHARS` 一致：超了后端 400，这里先拦一次并让律师看见还剩多少字 */
const NOTE_MAX_CHARS = 300

/**
 * 把「同事的判断」升为「项目事实」的确认弹窗。
 *
 * ## 为什么必须弹窗、且允许改写
 *
 * 模型写的只是判断，人点一下才成为项目事实——这一步是整套记忆设计的闸门，
 * 所以不能做成「点了就确认」：律师得先看清这条到底写的是什么。反过来，助手
 * 起草的那句话常常带着上下文（「如上所述」「这个方案」），直接升为事实后别的
 * 会话读到会读不懂，因此预填原文、允许就地改准，比逼律师回助手重写一遍现实。
 *
 * 这个动作**不弹后端审批**（审批在 MCP 工具那侧），所以弹窗里必须写清后果：
 * 确认后本项目所有律师都会把它当已确认的事实使用。
 */
export function ProjectNoteConfirmDialog({
  note,
  contractId,
  onClose,
}: {
  /** null = 关闭；非空 = 正在确认这条「同事的判断」 */
  note: ProjectNote | null
  /** 确认成功后失效这份笔记列表（该条会从「同事的判断」移到「已确认的事实」） */
  contractId: number
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState('')
  const { mutate, isPending, reset } = useMutation({
    mutationFn: (input: { id: string; content?: string }) => confirmProjectNote(input.id, input.content),
    onSuccess: () => {
      toast.success('已确认为本项目的项目事实')
      void queryClient.invalidateQueries({ queryKey: workbenchKeys.projectNotes(contractId) })
      onClose()
    },
    // 失败不关弹窗：律师可能刚把一句话改到一半，关掉就把输入丢了
    onError: (error) => toast.error(errMessage(error, '确认失败，请稍后重试')),
  })

  // 换一条笔记就把草稿重置回它的原文，别把上一条的改写带到下一条上
  useEffect(() => {
    if (!note) return
    setDraft(note.content)
    reset()
  }, [note, reset])

  const close = () => {
    if (!isPending) onClose()
  }

  const submit = () => {
    if (!note) return
    const text = draft.trim()
    if (!text) {
      toast.error('确认的内容不能为空')
      return
    }
    // 没改写就不传 content（后端把「没传」当保留原文，传值才是改写）
    mutate({ id: note.id, content: text === note.content.trim() ? undefined : text })
  }

  return (
    <Dialog open={note !== null} onOpenChange={(open) => !open && close()}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>确认为项目事实</DialogTitle>
          <DialogDescription>
            确认后本项目的所有律师都会把它当已确认的事实使用。原文已带入下方，哪里说得不准可以直接改。
          </DialogDescription>
        </DialogHeader>
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={NOTE_MAX_CHARS}
          rows={5}
          aria-label="确认的内容"
        />
        <div className="text-right text-[11px] text-muted-foreground tabular-nums">
          {draft.length}/{NOTE_MAX_CHARS}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={close} disabled={isPending}>
            取消
          </Button>
          <Button onClick={submit} disabled={isPending || !draft.trim()}>
            {isPending ? '确认中…' : '确认为项目事实'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
