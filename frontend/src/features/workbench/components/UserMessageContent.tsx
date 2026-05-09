/** 用户消息内容（支持编辑重发） */

import { useState, useRef, useEffect, useCallback } from 'react'
import { Pencil } from 'lucide-react'
import { Textarea } from '@/components/ui/textarea'
import { useWorkbenchStore } from '../stores/workbench-store'
import type { WorkbenchMessage } from '../types'

export function UserMessageContent({ message }: { message: WorkbenchMessage }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(message.content)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const editAndResend = useWorkbenchStore((s) => s.editAndResend)
  const isStreaming = useWorkbenchStore((s) => s.isStreaming)

  useEffect(() => {
    if (editing) {
      textareaRef.current?.focus()
      textareaRef.current?.select()
    }
  }, [editing])

  const handleSave = useCallback(() => {
    const trimmed = value.trim()
    if (trimmed && trimmed !== message.content) {
      editAndResend(message.id, trimmed)
    }
    setEditing(false)
  }, [value, message.content, message.id, editAndResend])

  if (editing) {
    return (
      <div className="space-y-2">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSave() }
            if (e.key === 'Escape') { setValue(message.content); setEditing(false) }
          }}
          className="min-h-[44px] resize-none bg-primary-foreground/10 text-primary-foreground placeholder:text-primary-foreground/50"
        />
        <div className="flex gap-1.5 justify-end text-xs">
          <button
            onClick={() => { setValue(message.content); setEditing(false) }}
            className="px-2 py-0.5 rounded hover:bg-primary-foreground/20"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            className="px-2 py-0.5 rounded bg-primary-foreground/20 hover:bg-primary-foreground/30"
          >
            重发
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="group/content relative">
      <div className="whitespace-pre-wrap break-words">{message.content}</div>
      {!isStreaming && (
        <button
          onClick={() => setEditing(true)}
          className="absolute -top-1 -right-1 hidden group-hover/content:flex items-center justify-center size-6 rounded bg-primary-foreground/20 text-primary-foreground hover:bg-primary-foreground/30"
          title="编辑并重发"
        >
          <Pencil className="size-3" />
        </button>
      )}
    </div>
  )
}
