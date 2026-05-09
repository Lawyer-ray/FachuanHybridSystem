/** 会话列表项 */

import { Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatFileSize } from '@/lib/file-utils'

interface SessionItemProps {
  session: {
    id: number
    title: string
    last_message_preview: string
    message_count?: number
    storage_bytes?: number
  }
  isActive: boolean
  onSelect: () => void
  onDelete: () => void
}

export function SessionItem({ session, isActive, onSelect, onDelete }: SessionItemProps) {
  return (
    <div
      onClick={onSelect}
      className={cn(
        'group flex flex-col rounded-md px-2.5 py-2 cursor-pointer hover:bg-accent',
        isActive && 'bg-accent',
      )}
    >
      <div className="flex items-center">
        <span className="flex-1 min-w-0 text-sm truncate">{session.title || '新会话'}</span>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          className="shrink-0 ml-1 opacity-0 text-muted-foreground hover:text-destructive group-hover:opacity-100"
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>
      {session.last_message_preview && (
        <span className="text-[11px] text-muted-foreground truncate mt-0.5">
          {session.last_message_preview}
        </span>
      )}
      {session.message_count !== undefined && (
        <span className="text-[10px] text-muted-foreground/60 mt-0.5">
          {session.message_count} 条消息 · {formatFileSize(session.storage_bytes || 0)}
        </span>
      )}
    </div>
  )
}
