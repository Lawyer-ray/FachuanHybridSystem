/**
 * 单条会话行：行内重命名（inline 编辑）+ 后台任务徽章 + 悬停操作（重命名/删除）。
 *
 * 从 SessionSidebar 拆出（后者超软红线）。**重命名 mutation 不在这里**：
 * 每行各建一个 `useMutation` 就是每行一个 useQueryClient 订阅，100 条会话
 * 100 个订阅；现在由父层持有 `renameMutation`，本组件只把 {id, title} 下发，
 * `['copilot','sessions']` 的失效逻辑也就只有一处。
 *
 * 鼠标手势：单击进入 / 双击重命名 / 右键直接弹删除确认（这一行屏蔽浏览器默认菜单）。
 * 双击与右键是**鼠标专属**路径，所以 hover 才出现的铅笔与垃圾桶按钮必须保留——
 * 键盘用户和触屏用户没有等价手势，那两个按钮是它们唯一的重命名/删除入口。
 */

import { useState } from 'react'
import { MessageSquare, Pencil, Trash2 } from 'lucide-react'

import { formatSessionStamp, taskBadge } from '../../domain'
import type { AgentSession } from '../../types'
import { StatusBadge } from '@/components/shared/StatusBadge'

/**
 * 子按钮隔离：双击与右键是**行级**手势，从按钮冒泡到行容器会叠加成
 * 「右键垃圾桶 → 又弹一次删除确认」「双击垃圾桶 → 顺带进重命名」。
 *
 * 这里只 `stopPropagation()`、不 `preventDefault()`：右键按钮时浏览器系统菜单照常弹。
 * 理由是按钮本来就有 aria-label 且在 tab 序里，用户要的是行上的手势；在按钮上再
 * 屏蔽一次浏览器菜单只会多一处「右键失灵」，收益为零。两个按钮共用这一个 handler，
 * 避免四处 inline 写漏一处就复发上面的叠加。
 */
const isolateRowGesture = (e: React.MouseEvent) => e.stopPropagation()

/**
 * 子按钮的按键隔离（与 isolateRowGesture 同理，但按键走的不是 MouseEvent）。
 *
 * 行容器对 Enter/Space 做 `preventDefault()` + `onSwitch()`；按键从按钮冒泡上去
 * 就会被它吃掉：键盘用户在「重命名」上按 Enter 既不进编辑态（默认激活被 preventDefault
 * 掉了），还会被切到另一个会话。按钮自己的 Enter 激活由浏览器完成，这里只拦冒泡。
 */
const isolateRowKeyGesture = (e: React.KeyboardEvent) => e.stopPropagation()

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

  /** 进编辑态：铅笔按钮与行双击走同一条，删了按钮就只剩鼠标能用（见文件头） */
  const startRename = () => {
    setDraft(session.title)
    setEditing(true)
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
          // autoFocus 之后紧跟一次全选：双击进来是为了改名，不是追加
          onFocus={(e) => e.currentTarget.select()}
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
      onDoubleClick={startRename}
      onContextMenu={(e) => {
        // 只在本行 preventDefault：全局屏蔽会把正文区右键的复制/翻译/检查一起吃掉
        e.preventDefault()
        onRequestDelete()
      }}
      onKeyDown={(e) => {
        // 键盘用户必须能切会话。内层按钮各自 stopPropagation（见 isolateRowKeyGesture），
        // 所以这里的 preventDefault 只作用于行本身，不会吃掉按钮的 Enter 激活。
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
          {formatSessionStamp(session.updated_at)}
        </span>
      )}
      <span className="hidden flex-none gap-0.5 group-hover:flex">
        <button
          type="button"
          className="flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground hover:bg-card hover:text-foreground"
          aria-label="重命名"
          onClick={(e) => {
            e.stopPropagation()
            startRename()
          }}
          onDoubleClick={isolateRowGesture}
          onContextMenu={isolateRowGesture}
          onKeyDown={isolateRowKeyGesture}
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
          onDoubleClick={isolateRowGesture}
          onContextMenu={isolateRowGesture}
          onKeyDown={isolateRowKeyGesture}
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </span>
    </div>
  )
}
