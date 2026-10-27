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
 *
 * 本文件只留外壳（queries / mutations / rail 拖宽 / 记忆入口）；会话行、分组块、
 * 用量摘要、删除确认分别在 `session/` 下。**重命名与删除两个 mutation 都在
 * 这一层**：放到行内就是每行一个 useQueryClient 订阅（100 条会话 100 个），
 * 且 `['copilot','sessions']` 的失效逻辑会散落成多处。
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Brain, Plus, X } from 'lucide-react'

import { deleteSession, listSessions, renameSession } from '../api'
import { MemoryDrawer } from './memory/MemoryDrawer'
import { groupSessions } from '../domain'
import { useRailResize } from '../hooks/use-rail-resize'
import { useCopilot } from '../store'
import type { AgentSession, SessionGroup } from '../types'
import { EmptyBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { Button } from '@/components/ui/button'
import { DeleteSessionDialog } from './session/DeleteSessionDialog'
import { SessionGroupBlock } from './session/SessionGroupBlock'
import { UsageFooter } from './session/UsageFooter'

/** overlay 形态右上角的收起钮（已有 aria-label，样式抽出来只为压行宽） */
const CLOSE_BUTTON_CLASS = 'ml-auto flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground'

interface SessionSidebarProps {
  variant: 'rail' | 'overlay'
  onClose?: () => void
  /** 所属面板宽度（rail 形态用它钳制侧栏可拖上限，保证对话区留够宽度） */
  panelWidth?: number
}

export function SessionSidebar({ variant, onClose, panelWidth = 0 }: SessionSidebarProps) {
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
  const currentGroupKey = context ? `${context.origin}:${context.refId}` : null

  const renameMutation = useMutation({
    mutationFn: (payload: { id: string; title: string }) => renameSession(payload.id, payload.title),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['copilot', 'sessions'] }),
  })

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
  /** 根节点：rail 形态与对话区并列；overlay 形态绝对定位盖满面板 */
  const rootClass = isRail
    ? 'relative flex flex-none flex-col border-r border-border bg-card'
    : 'absolute inset-0 z-20 flex animate-in slide-in-from-left flex-col border-r border-border bg-card duration-200'
  /** 默认展开规则：当前项目 + 最高位的分组展开，其余项目收起——照 ZCode
   *  「只展开你正在干活/最近用的文件夹，其余是收起的项目行」。通用对话/后台
   *  任务没有项目归属，不作折叠（它们不是「项目」，藏起来只会让人以为历史丢了）。 */
  const collapsedOf = (g: SessionGroup, i: number) => {
    const isCurrent = g.key === currentGroupKey
    const isUngrouped = g.kind === 'chat' || g.kind === 'task'
    const fallback = !isUngrouped && !isCurrent && i > 0
    return { isCurrent, collapsed: collapsedGroups[g.key] ?? fallback }
  }
  /** 切会话：已是当前会话就不重复切；两种形态点完都收起覆盖层 */
  const handleSwitch = (s: AgentSession) => {
    if (s.session_id !== sessionId) void switchSession(s.session_id)
    onClose?.()
  }
  /** 新对话：落回空白会话（send 用 store.context 建会话，归属天然正确） */
  const handleNewSession = () => {
    void switchSession(null)
    onClose?.()
  }
  /** 底部「助手记忆」入口：与用量摘要同区，属「关于这个助手」的一组 */
  const memoryEntryClass = 'flex w-full items-center gap-1.5 rounded-[7px] px-2 py-1.5 text-left text-[12px] text-muted-foreground transition-colors hover:bg-secondary/70 hover:text-foreground'

  return (
    <div
      className={rootClass}
      ref={isRail ? setRailRef : undefined}
      // rail 宽度走 CSS 变量：拖动中直改它，不触发整树重渲染
      style={isRail ? ({ '--copilot-rail-w': `${railWidth}px`, width: 'var(--copilot-rail-w)' } as React.CSSProperties) : undefined}
    >
      {/* 右缘拖宽把手：默认 180px 时客户全称被截成（委托方全称被截断），
          隔着几个项目分不清；拖宽即可读全名（宽度持久化） */}
      {isRail && (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="调整会话列表宽度"
          onPointerDown={onHandlePointerDown}
          data-testid="copilot-rail-handle"
          className="absolute top-0 right-0 bottom-0 z-30 w-1.5 translate-x-1/2 cursor-col-resize touch-none transition-colors hover:bg-foreground/20"
        />
      )}
      <header className="flex h-10 flex-none items-center gap-2 border-b border-border px-3">
        <span className="text-[12.5px] font-semibold text-foreground">对话</span>
        {variant === 'overlay' && (
          <button type="button" onClick={onClose} aria-label="收起对话列表" className={CLOSE_BUTTON_CLASS}>
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </header>

      <div className="flex-none p-2">
        <Button variant="outline" size="sm" onClick={handleNewSession} className="h-8 w-full justify-start gap-1.5 text-[12.5px]">
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
          const { isCurrent, collapsed } = collapsedOf(g, i)
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
              onRename={(id, title) => renameMutation.mutate({ id, title })}
              onSwitch={handleSwitch}
            />
          )
        })}
      </div>

      <div className="flex-none border-t border-border px-2 py-1.5">
        <button type="button" onClick={() => setMemoryOpen(true)} className={memoryEntryClass}>
          <Brain className="h-3.5 w-3.5 opacity-70" />
          助手记忆
        </button>
      </div>

      <MemoryDrawer open={memoryOpen} onOpenChange={setMemoryOpen} />
      <UsageFooter />
      <DeleteSessionDialog target={confirmTarget} pending={deleteMutation.isPending} onCancel={() => setConfirmTarget(null)} onConfirm={(id) => deleteMutation.mutate(id)} />
    </div>
  )
}
