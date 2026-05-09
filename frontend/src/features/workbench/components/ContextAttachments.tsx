/** 上下文附件面板 — 在输入框上方显示已上传的附件 */

import { useRef, useCallback } from 'react'
import { Paperclip, X, FileText, Loader2, AlertCircle, Upload } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useWorkbenchStore } from '../stores/workbench-store'
import type { Attachment } from '../types'

export function ContextAttachments() {
  const attachments = useWorkbenchStore((s) => s.attachments)
  const addAttachment = useWorkbenchStore((s) => s.addAttachment)
  const removeAttachment = useWorkbenchStore((s) => s.removeAttachment)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = useCallback(
    async (files: FileList | null) => {
      if (!files) return
      for (const file of Array.from(files)) {
        await addAttachment(file)
      }
    },
    [addAttachment],
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      handleFileSelect(e.dataTransfer.files)
    },
    [handleFileSelect],
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  if (attachments.length === 0) {
    return (
      <div
        className="flex items-center gap-2"
        onDrop={handleDrop}
        onDragOver={handleDragOver}
      >
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-1 rounded-md border border-dashed border-border/60 px-2 py-1 text-[11px] text-muted-foreground hover:border-primary/40 hover:text-foreground transition-colors"
        >
          <Paperclip className="size-3" />
          添加附件
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png"
          className="hidden"
          onChange={(e) => handleFileSelect(e.target.files)}
        />
      </div>
    )
  }

  return (
    <div
      className="space-y-1.5"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-muted-foreground">附件:</span>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-1 rounded border border-dashed border-border/60 px-1.5 py-0.5 text-[10px] text-muted-foreground hover:border-primary/40 hover:text-foreground transition-colors"
        >
          <Upload className="size-2.5" />
          添加
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png"
          className="hidden"
          onChange={(e) => handleFileSelect(e.target.files)}
        />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {attachments.map((att) => (
          <AttachmentChip
            key={att.id}
            attachment={att}
            onRemove={() => removeAttachment(att.id)}
          />
        ))}
      </div>
    </div>
  )
}

function AttachmentChip({
  attachment,
  onRemove,
}: {
  attachment: Attachment
  onRemove: () => void
}) {
  const icon =
    attachment.status === 'uploading' || attachment.status === 'processing' ? (
      <Loader2 className="size-3 animate-spin text-muted-foreground" />
    ) : attachment.status === 'error' ? (
      <AlertCircle className="size-3 text-destructive" />
    ) : (
      <FileText className="size-3 text-muted-foreground" />
    )

  const label =
    attachment.name.length > 20
      ? attachment.name.slice(0, 10) + '...' + attachment.name.slice(-7)
      : attachment.name

  return (
    <div
      className={cn(
        'group flex items-center gap-1 rounded-md border bg-background/80 px-2 py-1 text-[11px]',
        attachment.status === 'error' && 'border-destructive/40',
        attachment.status === 'ready' && 'border-border/60',
      )}
      title={attachment.error || attachment.name}
    >
      {icon}
      <span className={cn('truncate max-w-[120px]', attachment.status === 'error' && 'text-destructive')}>
        {label}
      </span>
      {attachment.status === 'ready' && (
        <span className="text-[10px] text-muted-foreground">{formatSize(attachment.size)}</span>
      )}
      <button
        type="button"
        onClick={onRemove}
        className="ml-0.5 rounded p-0.5 text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <X className="size-2.5" />
      </button>
    </div>
  )
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / (1024 * 1024)).toFixed(1) + 'MB'
}
