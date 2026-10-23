/**
 * 会话列表：新对话 / 切换 / 行内重命名 / 删除（确认后执行）。
 *
 * 两种形态共用本组件（variant）：
 * - rail：md+ 常驻窄栏（面板双栏布局的左列），无关闭钮、无滑入动画；
 * - overlay：sm 以下覆盖层（从左滑入盖住对话区），composer 仍可输入。
 *
 * 删除语义：删除当前会话时由**相邻会话顺位接管**（先下后上，无剩余才落
 * 空白新对话），列表保持原位不跳转；删非当前会话则什么都不动。
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Pencil, Plus, Trash2, X } from 'lucide-react'

import { deleteSession, getUsageSummary, listSessions, renameSession } from '../api'
import { taskBadge } from '../domain'
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

function SessionRow({
  session,
  active,
  compact,
  onSwitch,
  onRequestDelete,
}: {
  session: AgentSession
  active: boolean
  /** rail 窄栏：隐藏日期只留标题 */
  compact: boolean
  onSwitch: () => void
  onRequestDelete: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const queryClient = useQueryClient()

  const renameMutation = useMutation({
    mutationFn: (title: string) => renameSession(session.session_id, title),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['copilot', 'sessions'] }),
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

  const badge = taskBadge(session.task_state)

  return (
    <div
      role="button"
      tabIndex={0}
      aria-current={active ? 'true' : undefined}
      className={`group flex cursor-pointer items-center gap-2 rounded-[8px] px-2 py-2 text-[13px] transition-colors ${
        active ? 'bg-secondary text-foreground' : 'text-secondary-foreground hover:bg-secondary/60'
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
      <MessageSquare className="h-3.5 w-3.5 flex-none text-muted-foreground" />
      <span className="min-w-0 flex-1 truncate">{session.title || '未命名对话'}</span>
      {badge && (
        <span
          className={`flex-none rounded-[4px] px-1 py-px text-[10px] leading-4 ${badge.cls}`}
          title={`后台任务：${badge.label}`}
        >
          {badge.label}
        </span>
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

/** 个人本月用量摘要（P1-2）：失败率非零才显示，保持一行克制 */
function UsageFooter() {
  const { data } = useQuery({
    queryKey: ['copilot', 'usage', 30],
    queryFn: () => getUsageSummary(30),
    staleTime: 300_000,
    retry: false,
  })
  if (!data || data.runs === 0) return null
  const tokens = data.total_tokens >= 10000 ? `${(data.total_tokens / 1000).toFixed(1)}k` : String(data.total_tokens)
  const errPct = data.error_rate > 0 ? `${(data.error_rate * 100).toFixed(data.error_rate < 0.1 ? 1 : 0)}%` : ''
  const avg = data.avg_duration_ms >= 1000 ? `${(data.avg_duration_ms / 1000).toFixed(1)}s` : `${data.avg_duration_ms}ms`
  return (
    <div
      className="mt-auto flex-none border-t border-border px-3 py-2 text-[11px] leading-relaxed text-muted-foreground"
      title={`近 30 天：${data.runs} 轮（完成 ${data.ok_runs} / 出错 ${data.error_runs} / 中止 ${data.cancelled_runs}），输入 ${data.input_tokens} + 输出 ${data.output_tokens} tokens，工具调用 ${data.tool_calls} 次`}
    >
      近 30 天 {data.runs} 轮 · {tokens} tokens · 均耗 {avg}
      {errPct && <span className="text-destructive/80"> · 失败 {errPct}</span>}
    </div>
  )
}

export function SessionSidebar({
  variant,
  onClose,
}: {
  variant: 'rail' | 'overlay'
  onClose?: () => void
}) {
  const sessionId = useCopilot((s) => s.sessionId)
  const context = useCopilot((s) => s.context)
  const switchSession = useCopilot((s) => s.switchSession)
  const queryClient = useQueryClient()
  const [confirmTarget, setConfirmTarget] = useState<AgentSession | null>(null)

  const scopeKey = context ? `${context.origin}:${context.refId}` : 'all'
  const scope = context ? { origin: context.origin, refId: context.refId } : undefined
  const sessionsQuery = useQuery({
    queryKey: ['copilot', 'sessions', scopeKey],
    queryFn: () => listSessions(50, scope),
    refetchOnMount: 'always',
    retry: false,
    // 有排队/运行中的后台任务时轮询：状态落到 succeeded/failed 即停
    refetchInterval: (query) => {
      const data = query.state.data
      return data?.some((s) => s.task_state === 'queued' || s.task_state === 'running') ? 4000 : false
    },
  })
  const sessions = sessionsQuery.data ?? []

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteSession(id),
    onSuccess: (_data, id) => {
      // 顺位接管：删的是当前会话时选相邻会话（先下后上），无剩余才落新对话
      const index = sessions.findIndex((s) => s.session_id === id)
      const next = sessions[index + 1] ?? sessions[index - 1]
      if (id === sessionId) void switchSession(next?.session_id ?? null)
      void queryClient.invalidateQueries({ queryKey: ['copilot', 'sessions'] })
    },
  })

  const rootClass =
    variant === 'rail'
      ? 'flex w-[180px] flex-none flex-col border-r border-border bg-card'
      : 'absolute inset-0 z-20 flex animate-in slide-in-from-left flex-col border-r border-border bg-card duration-200'

  return (
    <div className={rootClass}>
      <header className="flex h-10 flex-none items-center gap-2 border-b border-border px-3">
        <span className="text-[12.5px] font-semibold text-foreground">对话</span>
        {variant === 'overlay' && (
          <button
            type="button"
            className="ml-auto flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            onClick={onClose}
            aria-label="收起对话列表"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </header>

      <div className="flex-none p-2">
        <Button
          variant="outline"
          size="sm"
          className="h-8 w-full justify-start gap-1.5 text-[12.5px]"
          onClick={() => {
            void switchSession(null)
            onClose?.()
          }}
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
          新对话
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-1.5 pb-2">
        {sessionsQuery.isLoading && (
          <p className="py-4 text-center text-[12px] text-muted-foreground">加载中…</p>
        )}
        {!sessionsQuery.isLoading && sessions.length === 0 && (
          <p className="py-4 text-center text-[12px] text-muted-foreground">
            {context ? `「${context.title}」还没有 AI 会话` : '暂无历史会话'}
          </p>
        )}
        {sessions.map((s) => (
          <SessionRow
            key={s.session_id}
            session={s}
            active={s.session_id === sessionId}
            compact={variant === 'rail'}
            onRequestDelete={() => setConfirmTarget(s)}
            onSwitch={() => {
              if (s.session_id !== sessionId) void switchSession(s.session_id)
              onClose?.()
            }}
          />
        ))}
      </div>

      <UsageFooter />

      <AlertDialog open={confirmTarget !== null} onOpenChange={(v) => !v && setConfirmTarget(null)}>
        <AlertDialogContent className="max-w-[340px]">
          <AlertDialogHeader>
            <AlertDialogTitle>删除该对话？</AlertDialogTitle>
            <AlertDialogDescription>
              「{confirmTarget?.title || '未命名对话'}」的消息记录将一并删除，删除后无法恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              onClick={() => {
                if (confirmTarget) deleteMutation.mutate(confirmTarget.session_id)
                setConfirmTarget(null)
              }}
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
