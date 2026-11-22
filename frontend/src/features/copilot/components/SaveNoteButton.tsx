/**
 * 「存进项目笔记」——把这条回答里的结论落到项目上，同团队可见。
 *
 * ## 为什么需要这个按钮
 *
 * A 律师跟 AI 捋清楚的东西，换了会话就没了：pi session 按会话按人隔离，
 * 同事那边完全看不到，只能把同样的问题再问一遍。存成项目笔记之后，同团队
 * 任何人下次在这个项目/案件的会话里都会读到它（注入由后端快照完成）。
 *
 * ## 为什么只带 sessionId，不带 contract_id
 *
 * 前端拿不到可靠的 `contract_id`（`CopilotScope` 只有 origin+refId，案件页
 * 只发 case_id）。让前端猜锚点必然把结论写到错的项目上——所以锚点一律由
 * 服务端按会话归属反查（`POST /agent/memory/notes` 的 `session_id`）。
 *
 * ## 交互取舍
 *
 * 不直接「点了就存」：助手回答往往几百字，整段存进去会超出 300 字上限、
 * 也读不出结论。所以点开弹窗、预填一句话草稿、让律师删到能独立读懂为止。
 * 存进去的东西是要给同事当判断依据的，值得多一次确认。
 */

import { useState } from 'react'
import { BookmarkPlus } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'

import { createProjectNote } from '../api'
import { markdownToPlainText } from '../domain'
import { useCopilot } from '../store'

/** 与后端 `write.NOTE_MAX_CHARS` 一致；超了后端 400，前端先拦一次说人话 */
const NOTE_MAX_CHARS = 300

export function SaveNoteButton({ content }: { content: string }) {
  const sessionId = useCopilot((s) => s.sessionId)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const disabled = !sessionId

  const openDialog = () => {
    // 预填一句话草稿：去掉 Markdown 标记、压成单行、截到上限。
    // 律师改一句比从零写快得多，也比整段照搬有用。
    setDraft(markdownToPlainText(content).replace(/\s+/g, ' ').trim().slice(0, NOTE_MAX_CHARS))
    setOpen(true)
  }

  const save = async () => {
    if (!sessionId) return
    const text = draft.trim()
    if (!text) {
      toast.error('笔记内容不能为空')
      return
    }
    setSaving(true)
    try {
      await createProjectNote({ content: text, sessionId })
      toast.success('已存进项目笔记，同团队可见')
      setOpen(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      {/* 与复制按钮同一套显隐：常显会让每条回答下面挂一排图标，长转录里噪音盖过正文 */}
      <span className="inline-flex items-center opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        <button
          type="button"
          aria-label="存进项目笔记"
          aria-disabled={disabled ? true : undefined}
          title={disabled ? '本会话还没落库，暂时存不了笔记' : '存进项目笔记（同团队所有律师可见）'}
          className={
            'flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary ' +
            (disabled ? 'cursor-not-allowed opacity-40' : 'hover:text-foreground')
          }
          onClick={() => {
            if (disabled) return
            openDialog()
          }}
        >
          <BookmarkPlus className="h-3 w-3" aria-hidden />
        </button>
      </span>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-[560px]">
          <DialogHeader>
            <DialogTitle>存进项目笔记</DialogTitle>
            <DialogDescription>
              存成一句能独立读懂的结论。**同团队所有律师**在该项目/案件的会话里都会看到它——不要写不该给同事看的内容。
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            maxLength={NOTE_MAX_CHARS}
            rows={5}
            aria-label="笔记内容"
            placeholder="一句话结论 + 理由，例如：对方已同意六个月内分期，底线 80 万不再让。"
          />
          <div className="text-right text-[11px] text-muted-foreground tabular-nums">
            {draft.length}/{NOTE_MAX_CHARS}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)} disabled={saving}>
              取消
            </Button>
            <Button onClick={() => void save()} disabled={saving || !draft.trim()}>
              {saving ? '保存中…' : '存进笔记'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
