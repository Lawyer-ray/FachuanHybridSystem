/**
 * 面板内会话侧边栏：新对话 / 切换 / 行内重命名 / 删除（确认后执行）。
 * 以覆盖层形式盖在消息区上方（从左滑入），composer 仍可输入。
 * 会话列表走 react-query；改名/删除后失效重拉，删除当前会话则切到新对话。
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Pencil, Plus, Trash2, X } from 'lucide-react'

import { deleteSession, listSessions, renameSession } from '../api'
import { useCopilot } from '../store'
import type { AgentSession } from '../types'
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
import { Button } from '@/components/ui/button'

function formatTime(iso: string): string {
  return iso.replace('T', ' ').slice(5, 16)
}

function SessionRow({
  session,
  active,
  onSwitch,
}: {
  session: AgentSession
  active: boolean
  onSwitch: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const queryClient = useQueryClient()
  const switchSession = useCopilot((s) => s.switchSession)

  const renameMutation = useMutation({
    mutationFn: (title: string) => renameSession(session.session_id, title),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['copilot', 'sessions'] }),
  })
  const deleteMutation = useMutation({
    mutationFn: () => deleteSession(session.session_id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['copilot', 'sessions'] })
      if (active) void switchSession(null)
    },
  })

  const commitRename = () => {
    const title = draft.trim()
    setEditing(false)
    if (title && title !== session.title) renameMutation.mutate(title)
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

  return (
    <div
      className={`group flex cursor-pointer items-center gap-2 rounded-[8px] px-2 py-2 text-[13px] transition-colors ${
        active ? 'bg-secondary text-foreground' : 'text-secondary-foreground hover:bg-secondary/60'
      }`}
      onClick={onSwitch}
    >
      <MessageSquare className="h-3.5 w-3.5 flex-none text-muted-foreground" />
      <span className="min-w-0 flex-1 truncate">{session.title || '未命名对话'}</span>
      <span className="flex-none text-[11px] text-muted-foreground">{formatTime(session.updated_at)}</span>
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
            setConfirmDelete(true)
          }}
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </span>

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent className="max-w-[340px]">
          <AlertDialogHeader>
            <AlertDialogTitle>删除该对话？</AlertDialogTitle>
            <AlertDialogDescription>
              「{session.title || '未命名对话'}」的消息记录将一并删除，删除后无法恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              onClick={() => deleteMutation.mutate()}
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export function SessionSidebar({ onClose }: { onClose: () => void }) {
  const sessionId = useCopilot((s) => s.sessionId)
  const switchSession = useCopilot((s) => s.switchSession)

  const sessionsQuery = useQuery({
    queryKey: ['copilot', 'sessions'],
    queryFn: () => listSessions(50),
    refetchOnMount: 'always',
    retry: false,
  })
  const sessions = sessionsQuery.data ?? []

  return (
    <div className="absolute inset-0 z-20 flex animate-in slide-in-from-left flex-col border-r border-border bg-card duration-200">
      <header className="flex h-10 flex-none items-center gap-2 border-b border-border px-3">
        <span className="text-[12.5px] font-semibold text-foreground">对话</span>
        <button
          type="button"
          className="ml-auto flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={onClose}
          aria-label="收起对话列表"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </header>

      <div className="flex-none p-2">
        <Button
          variant="outline"
          size="sm"
          className="h-8 w-full justify-start gap-1.5 text-[12.5px]"
          onClick={() => {
            void switchSession(null)
            onClose()
          }}
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
          新对话
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto px-1.5 pb-2">
        {sessionsQuery.isLoading && (
          <p className="py-4 text-center text-[12px] text-muted-foreground">加载中…</p>
        )}
        {!sessionsQuery.isLoading && sessions.length === 0 && (
          <p className="py-4 text-center text-[12px] text-muted-foreground">暂无历史会话</p>
        )}
        {sessions.map((s) => (
          <SessionRow
            key={s.session_id}
            session={s}
            active={s.session_id === sessionId}
            onSwitch={() => {
              if (s.session_id !== sessionId) void switchSession(s.session_id)
              onClose()
            }}
          />
        ))}
      </div>
    </div>
  )
}
