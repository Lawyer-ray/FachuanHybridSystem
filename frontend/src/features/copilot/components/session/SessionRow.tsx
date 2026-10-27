/**
 * 单条会话行：行内重命名（inline 编辑）+ 后台任务徽章 + 悬停操作（重命名/删除）。
 *
 * 从 SessionSidebar 拆出（后者超软红线）。**重命名 mutation 不在这里**：
 * 每行各建一个 `useMutation` 就是每行一个 useQueryClient 订阅，100 条会话
 * 100 个订阅；现在由父层持有 `renameMutation`，本组件只把 {id, title} 下发，
 * `['copilot','sessions']` 的失效逻辑也就只有一处。
 */

import { useState } from 'react'
import { MessageSquare, Pencil, Trash2 } from 'lucide-react'

import { taskBadge } from '../../domain'
import type { AgentSession } from '../../types'
import { StatusBadge } from '@/components/shared/status-badge'

export function SessionRow({
  session,
  active,
  compact,
  onSwitch,
  onRequestDelete,
  onRename,
}: {
  session: AgentSession
  active: boolean
  /** rail 窄栏：隐藏日期只留标题 */
  compact: boolean
  onSwitch: () => void
  onRequestDelete: () => void
  /** 提交重命名（父层统一持有 mutation，见文件头） */
  onRename: (id: string, title: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  const commitRename = () => {
    const title = draft.trim()
    setEditing(false)
    if (title && title !== session.title) onRename(session.session_id, title)
  }

  if (editing) {
    return (
      <div className="px-1.5 py-1">
        <input
          autoFocus
          value={draft}
          maxLength={60}
          className="w-full rounded-[8px] border border-input bg-background px-2 py-1.5 text-[13px] text-foreground outline-none focus:border-foreground/40"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitRename()
            if (e.key === 'Escape') setEditing(false)
          }}
          onBlur={commitRename}
        />
      </div>
    )
  }

  const badge = taskBadge(session.task_state)

  return (
    <div
      role="button"
      tabIndex={0}
      aria-current={active ? 'true' : undefined}
      className={`group relative flex cursor-pointer items-center gap-1.5 rounded-[7px] py-1.5 pr-1.5 pl-2 text-[12.5px] transition-colors ${
        active
          ? 'bg-secondary font-medium text-foreground'
          : 'text-secondary-foreground hover:bg-secondary/50'
      }`}
      onClick={onSwitch}
      onKeyDown={(e) => {
        // 键盘用户必须能切会话；内层按钮的按键不冒泡到这里
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSwitch()
        }
      }}
    >
      <MessageSquare className={`h-3 w-3 flex-none ${active ? 'text-foreground/70' : 'text-muted-foreground/70'}`} />
      <span className="min-w-0 flex-1 truncate">{session.title || '未命名对话'}</span>
      {badge && (
        <StatusBadge tone={badge.tone} size="xs" className="flex-none" title={`后台任务：${badge.label}`}>
          {badge.label}
        </StatusBadge>
      )}
      {!compact && (
        <span className="flex-none text-[11px] text-muted-foreground">
          {session.updated_at.replace('T', ' ').slice(5, 16)}
        </span>
      )}
      <span className="hidden flex-none gap-0.5 group-hover:flex">
        <button
          type="button"
          className="flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground hover:bg-card hover:text-foreground"
          aria-label="重命名"
          onClick={(e) => {
            e.stopPropagation()
            setDraft(session.title)
            setEditing(true)
          }}
        >
          <Pencil className="h-3 w-3" />
        </button>
        <button
          type="button"
          className="flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground hover:bg-card hover:text-destructive"
          aria-label="删除对话"
          onClick={(e) => {
            e.stopPropagation()
            onRequestDelete()
          }}
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </span>
    </div>
  )
}
