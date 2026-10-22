/**
 * 会话切换菜单：新对话 + 最近会话列表。
 * 会话列表是服务端状态，走 react-query，打开菜单时拉取（refetchOnMount 兜新会话）。
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { History, MessageSquarePlus, Plus } from 'lucide-react'

import { listSessions } from '../api'
import { useCopilot } from '../store'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export function SessionMenu() {
  const [open, setOpen] = useState(false)
  const sessionId = useCopilot((s) => s.sessionId)
  const switchSession = useCopilot((s) => s.switchSession)

  const sessionsQuery = useQuery({
    queryKey: ['copilot', 'sessions'],
    queryFn: () => listSessions(30),
    enabled: open,
    refetchOnMount: 'always',
    retry: false,
  })

  const sessions = sessionsQuery.data ?? []

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex h-7 w-7 items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          aria-label="会话列表"
        >
          <History className="h-4 w-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-[420px] w-64 overflow-y-auto">
        <DropdownMenuItem
          onSelect={() => {
            void switchSession(null)
          }}
        >
          <Plus className="h-3.5 w-3.5" />
          新对话
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {sessions.length === 0 && (
          <div className="px-2 py-3 text-center text-[12px] text-muted-foreground">暂无历史会话</div>
        )}
        {sessions.map((s) => (
          <DropdownMenuItem
            key={s.session_id}
            className={s.session_id === sessionId ? 'bg-secondary' : undefined}
            onSelect={() => {
              if (s.session_id !== sessionId) void switchSession(s.session_id)
            }}
          >
            <MessageSquarePlus className="h-3.5 w-3.5 flex-none" />
            <span className="truncate">{s.title || '新对话'}</span>
            <span className="ml-auto flex-none text-[11px] text-muted-foreground">
              {s.updated_at.slice(5, 10)}
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
