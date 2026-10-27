/**
 * 分组会话渲染：组头（文件夹层）折叠 + 组内「显示更多」（默认前 5 条）。
 *
 * 从 SessionSidebar 拆出（后者超软红线）。组头 = 文件夹，会话行挂在下面，
 * 层级靠「缩进 + 左缘贯通引导线」表达，而不是只靠图标区分。
 */

import { useState } from 'react'
import { Briefcase, ChevronRight, Clock3, MessageSquare, Scale } from 'lucide-react'

import type { AgentSession, SessionGroup } from '../../types'
import { SessionRow } from './SessionRow'

/** 组头图标：委托=公文包 / 案件=天平 / 任务=时钟 / 通用=对话 */
const GROUP_ICON: Record<SessionGroup['kind'], typeof Briefcase> = {
  contract: Briefcase,
  case: Scale,
  task: Clock3,
  chat: MessageSquare,
}

export function SessionGroupBlock({
  group,
  collapsed,
  current,
  onToggleCollapsed,
  compact,
  sessionId,
  onSwitch,
  onRequestDelete,
  onRename,
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
  onRename: (id: string, title: string) => void
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
              onRename={onRename}
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
