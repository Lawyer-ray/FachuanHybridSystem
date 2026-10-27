/**
 * 会话列表：新对话 / 切换 / 行内重命名 / 删除（确认后执行）。
 *
 * 布局照 ZCode 侧边栏：**始终展示全部会话，按项目（业务范围）分组**——
 * 一个项目 = 一个文件夹，会话平铺在它下面，组头可折叠、超 5 条显示
 * 「显示更多」。进项目页（context 有值）时不是把列表过滤成只剩本项目，
 * 而是该项目分组自动展开并高亮，其余项目仍在（律师常要在几个委托间
 * 来回跳）；此时「新对话」落进当前项目——send 用 store.context 建会话，
 * 归属天然正确。
 *
 * 历史教训：早先 context 模式直接按 scope 查后端、只列单一范围，等于进
 * 了项目就看不到别的项目会话，切换必须退出页面，与「项目=文件夹」的
 * 心智模型不符。
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
import { Brain, Briefcase, ChevronRight, Clock3, MessageSquare, Pencil, Plus, Scale, Trash2, X } from 'lucide-react'

import { deleteSession, getUsageSummary, listSessions, renameSession } from '../api'
import { MemoryDrawer } from './MemoryDrawer'
import { groupSessions, taskBadge } from '../domain'
import { useRailResize } from '../hooks/use-rail-resize'
import { useCopilot } from '../store'
import type { AgentSession, SessionGroup } from '../types'
import { EmptyBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { StatusBadge } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'

/** 组头图标：委托=公文包 / 案件=天平 / 任务=时钟 / 通用=对话 */
const GROUP_ICON: Record<SessionGroup['kind'], typeof Briefcase> = {
  contract: Briefcase,
  case: Scale,
  task: Clock3,
  chat: MessageSquare,
}

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

/** 分组会话渲染：组头折叠 + 组内「显示更多」（默认前 5 条） */
function SessionGroupBlock({
  group,
  collapsed,
  current,
  onToggleCollapsed,
  compact,
  sessionId,
  onSwitch,
  onRequestDelete,
}: {
  group: SessionGroup
  collapsed: boolean
  /** 当前项目分组：组头加粗高亮，让律师一眼看到身在哪个委托 */
  current: boolean
  onToggleCollapsed: () => void
  compact: boolean
  sessionId: string | null
  onSwitch: (s: AgentSession) => void
  onRequestDelete: (s: AgentSession) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const VISIBLE = 5
  const visible = expanded ? group.sessions : group.sessions.slice(0, VISIBLE)
  const hidden = group.sessions.length - visible.length
  const Icon = GROUP_ICON[group.kind]
  return (
    <section aria-label={`会话分组 ${group.label}`} className="mb-1.5">
      {/* 组头 = 文件夹层：小字号 + 重字重 + 浅缩进，与下层会话行拉开层级；
          当前项目在左缘加一条实心强调条，和「你正站在这个委托里」对应 */}
      <button
        type="button"
        className={`relative flex w-full items-center gap-1.5 rounded-[7px] py-1.5 pr-2 pl-2.5 text-left transition-colors hover:bg-secondary/70 ${
          current ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
        }`}
        onClick={onToggleCollapsed}
        aria-expanded={!collapsed}
        aria-current={current ? 'true' : undefined}
      >
        {current && (
          <span aria-hidden className="absolute top-1.5 bottom-1.5 left-0 w-[2.5px] rounded-full bg-foreground" />
        )}
        <ChevronRight
          className={`h-3 w-3 flex-none opacity-60 transition-transform duration-150 ${collapsed ? '' : 'rotate-90'}`}
        />
        <Icon className={`h-3.5 w-3.5 flex-none ${current ? 'opacity-100' : 'opacity-70'}`} />
        <span
          className={`min-w-0 flex-1 truncate text-[12px] tracking-[0.01em] ${current ? 'font-[650]' : 'font-medium'}`}
          title={group.label}
        >
          {group.label}
        </span>
        {group.sessions.length > 1 && (
          <span className="flex-none rounded-[5px] bg-foreground/5 px-1.5 py-px text-[10.5px] leading-4 tabular-nums text-muted-foreground">
            {group.sessions.length}
          </span>
        )}
      </button>
      {!collapsed && (
        /* 会话区整体右移，并在左缘画一条贯通引导线：文件挂在文件夹下面，
           层级靠「缩进 + 引导线」表达，而不是只靠图标区分 */
        <div className="relative mt-0.5 mb-1 ml-[13px] space-y-px border-l border-border/70 pl-2">
          {visible.map((s) => (
            <SessionRow
              key={s.session_id}
              session={s}
              active={s.session_id === sessionId}
              compact={compact}
              onRequestDelete={() => onRequestDelete(s)}
              onSwitch={() => onSwitch(s)}
            />
          ))}
          {hidden > 0 && (
            <button
              type="button"
              className="w-full rounded-[6px] px-1.5 py-1.5 text-left text-[11.5px] text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
              onClick={() => setExpanded(true)}
            >
              显示更多（{hidden}）
            </button>
          )}
        </div>
      )}
    </section>
  )
}

export function SessionSidebar({
  variant,
  onClose,
  panelWidth = 0,
}: {
  variant: 'rail' | 'overlay'
  onClose?: () => void
  /** 所属面板宽度（rail 形态用它钳制侧栏可拖上限，保证对话区留够宽度） */
  panelWidth?: number
}) {
  const sessionId = useCopilot((s) => s.sessionId)
  const context = useCopilot((s) => s.context)
  const switchSession = useCopilot((s) => s.switchSession)
  const queryClient = useQueryClient()
  const [confirmTarget, setConfirmTarget] = useState<AgentSession | null>(null)
  const { width: railWidth, setRailRef, onHandlePointerDown } = useRailResize(panelWidth)

  // 始终拉全量（后端按 updated_at 降序 + 注水 scope_name），侧栏按项目分组。
  // 不再按 scope 过滤：过滤后别的项目会话就消失了，与「项目=文件夹」不符。
  const sessionsQuery = useQuery({
    queryKey: ['copilot', 'sessions', 'all'],
    queryFn: () => listSessions(100),
    refetchOnMount: 'always',
    retry: false,
    // 有排队/运行中的后台任务时轮询：状态落到 succeeded/failed 即停
    refetchInterval: (query) => {
      const data = query.state.data
      return data?.some((s) => s.task_state === 'queued' || s.task_state === 'running') ? 4000 : false
    },
  })
  const sessions = sessionsQuery.data ?? []
  const groups = groupSessions(sessions)
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({})
  // 记忆抽屉：入口在侧边栏底部（与用量摘要同区，属「关于这个助手」的一组）
  const [memoryOpen, setMemoryOpen] = useState(false)
  /** 当前项目所在分组的 key（无 context 时为 null = 通用/任务视图） */
  const currentGroupKey = context
    ? `${context.origin}:${context.refId}`
    : null

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

  const isRail = variant === 'rail'
  const rootClass = isRail
    ? 'relative flex flex-none flex-col border-r border-border bg-card'
    : 'absolute inset-0 z-20 flex animate-in slide-in-from-left flex-col border-r border-border bg-card duration-200'

  return (
    <div
      className={rootClass}
      ref={isRail ? setRailRef : undefined}
      // rail 宽度走 CSS 变量：拖动中直改它，不触发整树重渲染
      style={isRail ? ({ '--copilot-rail-w': `${railWidth}px`, width: 'var(--copilot-rail-w)' } as React.CSSProperties) : undefined}
    >
      {isRail && (
        /* 右缘拖宽把手：默认 180px 时客户全称被截成（委托方全称被截断），
           隔着几个项目分不清；拖宽即可读全名（宽度持久化） */
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="调整会话列表宽度"
          className="absolute top-0 right-0 bottom-0 z-30 w-1.5 translate-x-1/2 cursor-col-resize touch-none transition-colors hover:bg-foreground/20"
          onPointerDown={onHandlePointerDown}
          data-testid="copilot-rail-handle"
        />
      )}
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
        {sessionsQuery.isLoading && <LoadingBlock className="py-4" />}
        {!sessionsQuery.isLoading && sessions.length === 0 && (
          <EmptyBlock className="py-4">
            {context ? `「${context.title}」还没有 AI 会话，问一句就会出现在这里` : '暂无历史会话'}
          </EmptyBlock>
        )}
        {groups.map((g, i) => {
          // 默认展开规则：当前项目 + 最高位的那个分组展开，其余项目收起——
          // 照 ZCode「只展开你正在干活/最近用的文件夹，其余是收起的项目行」。
          // 通用对话/后台任务没有项目归属，不作折叠（它们不是「项目」，
          // 藏起来只会让人以为历史丢了）。
          const isCurrent = g.key === currentGroupKey
          const ungrouped = g.kind === 'chat' || g.kind === 'task'
          const defaultCollapsed = !ungrouped && !isCurrent && i > 0
          const collapsed = collapsedGroups[g.key] ?? defaultCollapsed
          return (
            <SessionGroupBlock
              key={g.key}
              group={g}
              collapsed={collapsed}
              current={isCurrent}
              onToggleCollapsed={() => setCollapsedGroups((prev) => ({ ...prev, [g.key]: !collapsed }))}
              compact={variant === 'rail'}
              sessionId={sessionId}
              onRequestDelete={setConfirmTarget}
              onSwitch={(s) => {
                if (s.session_id !== sessionId) void switchSession(s.session_id)
                onClose?.()
              }}
            />
          )
        })}
      </div>

      <div className="flex-none border-t border-border px-2 py-1.5">
        <button
          type="button"
          className="flex w-full items-center gap-1.5 rounded-[7px] px-2 py-1.5 text-left text-[12px] text-muted-foreground transition-colors hover:bg-secondary/70 hover:text-foreground"
          onClick={() => setMemoryOpen(true)}
        >
          <Brain className="h-3.5 w-3.5 opacity-70" />
          助手记忆
        </button>
      </div>

      <MemoryDrawer open={memoryOpen} onOpenChange={setMemoryOpen} />

      <UsageFooter />

      <ConfirmDialog
        open={confirmTarget !== null}
        onOpenChange={(v) => !v && setConfirmTarget(null)}
        title="删除该对话？"
        description={`「${confirmTarget?.title || '未命名对话'}」的消息记录将一并删除，删除后无法恢复。`}
        confirmText="删除"
        tone="destructive"
        pending={deleteMutation.isPending}
        onConfirm={() => {
          if (confirmTarget) deleteMutation.mutate(confirmTarget.session_id)
          setConfirmTarget(null)
        }}
      />
    </div>
  )
}
