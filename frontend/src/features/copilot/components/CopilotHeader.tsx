/**
 * Copilot 面板 header：会话栏开关、上下文范围、目录树、并排、后端、模型、新对话、收起。
 *
 * 从 CopilotPanel 拆出（后者撞 350 行软红线）。拆出的好处不止行数：这一行控件
 * 的可见条件互相独立，聚在一处才能一眼对照——尤其 agent 后端标识必须紧挨「新对话」，
 * 用户才会把它理解成「下一个会话用谁」而不是「当前会话可以换」（换不了，见
 * AgentBackendPicker）。
 *
 * 纯展示组件：所有状态与动作由 CopilotPanel 传入，避免两处各订阅一份 store。
 */

import { Columns2, FolderTree, PanelLeftClose, PanelLeftOpen, Plus, Sparkles, SquareStack, X } from 'lucide-react'

import type { CopilotContext } from '../types'
import { AgentBackendPicker } from './AgentBackendPicker'

export interface CopilotHeaderProps {
  /** 会话栏是否常驻（宽屏展开态）；窄屏时开关作用于覆盖式列表 */
  railVisible: boolean
  onToggleRail: () => void
  /** 业务内会话上下文（案件/合同页打开）；null = 普通对话 */
  context: CopilotContext | null
  onExitContext: () => void
  treeDrawerOpen: boolean
  onToggleTreeDrawer: () => void
  dockCapable: boolean
  docked: boolean
  onDockToggle?: () => void
  /** 当前会话标题（空串时显示默认「AI 助手」） */
  currentTitle: string
  /** 最近一轮实际使用的模型（空串不显示标签） */
  currentModel: string
  /** 当前会话的后端 kind；null = 还没有会话（后端可自由选） */
  currentAgentKind: string | null
  onNewSession: () => void
  onClose: () => void
}

export function CopilotHeader({
  railVisible,
  onToggleRail,
  context,
  onExitContext,
  treeDrawerOpen,
  onToggleTreeDrawer,
  dockCapable,
  docked,
  onDockToggle,
  currentTitle,
  currentModel,
  currentAgentKind,
  onNewSession,
  onClose,
}: CopilotHeaderProps) {
  return (
    <header className="flex h-12 flex-none items-center gap-1.5 border-b border-border px-2.5">
      <button
        type="button"
        className="flex h-7 w-7 flex-none items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        onClick={onToggleRail}
        aria-label={railVisible ? '收起会话栏' : '展开会话列表'}
        title={railVisible ? '收起会话栏' : '展开会话列表'}
      >
        {railVisible ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
      </button>
      <span className="copilot-orb ml-0.5 flex h-6 w-6 flex-none items-center justify-center rounded-[8px]" aria-hidden>
        <Sparkles className="h-3.5 w-3.5 text-background" strokeWidth={2.2} />
      </span>
      <span className="min-w-0 flex-1 truncate px-0.5 text-[13px] font-semibold text-foreground">
        {context ? `AI 助手 · ${context.title}` : currentTitle || 'AI 助手'}
      </span>
      {context && (
        <button
          type="button"
          className="flex h-7 max-w-40 flex-none items-center gap-1 rounded-[8px] bg-secondary px-2 text-[11.5px] text-muted-foreground transition-colors hover:text-foreground"
          onClick={onExitContext}
          aria-label="退出业务范围，回到全部会话"
          title={`当前只看「${context.title}」的会话，点击回到全部`}
        >
          <SquareStack className="h-3 w-3 flex-none" />
          <span className="truncate">{context.origin === 'case' ? '本案' : '本委托'}</span>
          <X className="h-3 w-3 flex-none" />
        </button>
      )}
      {context?.origin === 'contract' && (
        <button
          type="button"
          className={`flex h-7 flex-none items-center gap-1 rounded-[8px] px-2 text-[12px] transition-colors hover:bg-secondary hover:text-foreground ${
            treeDrawerOpen ? 'bg-secondary text-foreground' : 'text-muted-foreground'
          }`}
          onClick={onToggleTreeDrawer}
          aria-label={treeDrawerOpen ? '收起合同材料目录' : '展开合同材料目录'}
          aria-pressed={treeDrawerOpen}
          title="合同绑定文件夹目录树：把文件拖到输入区即可引用"
        >
          <FolderTree className="h-3.5 w-3.5" />
          材料
        </button>
      )}
      {dockCapable && onDockToggle && (
        <button
          type="button"
          className={`flex h-7 w-7 flex-none items-center justify-center rounded-[8px] transition-colors hover:bg-secondary hover:text-foreground ${
            docked ? 'bg-secondary text-foreground' : 'text-muted-foreground'
          }`}
          onClick={onDockToggle}
          aria-pressed={docked}
          aria-label={docked ? '切换为悬浮模式' : '切换为并排模式'}
          title={
            docked
              ? '并排模式中：页面内容让位同屏显示，点击切回悬浮覆盖'
              : '并排模式：页面内容自动让位，可与合同详情页并排对照'
          }
        >
          <Columns2 className="h-4 w-4" />
        </button>
      )}
      {/* agent 后端：没有当前会话时可切换（决定新会话用谁），有会话时只读 */}
      <AgentBackendPicker currentKind={currentAgentKind} />
      {currentModel && (
        <span
          className="hidden max-w-28 flex-none truncate rounded-[6px] bg-secondary px-1.5 py-0.5 text-[10.5px] text-muted-foreground sm:block"
          title={`当前模型：${currentModel}`}
        >
          {currentModel}
        </span>
      )}
      <button
        type="button"
        className="flex h-7 flex-none items-center gap-1 rounded-[8px] px-2 text-[12.5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        onClick={onNewSession}
      >
        <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
        新对话
      </button>
      <button
        type="button"
        className="flex h-7 w-7 flex-none items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        onClick={onClose}
        aria-label="收起 AI 助手"
      >
        <X className="h-4 w-4" />
      </button>
    </header>
  )
}
