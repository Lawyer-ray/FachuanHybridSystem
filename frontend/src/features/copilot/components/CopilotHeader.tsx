/**
 * Copilot 面板 header：会话栏开关、上下文范围、目录树、并排、模型、新对话、收起
 * （另加已建会话的后端名后缀，它不是控件）。
 *
 * 抽屉（CopilotPanel）与独立页（AssistantPage）共用：页面上没有「收起」语义，
 * 故 onClose 可缺省（不为页面造一个假的关闭按钮），并排按钮同理由 dockCapable 控制。
 *
 * 从 CopilotPanel 拆出（后者撞 350 行软红线）。拆出的好处不止行数：这一行控件
 * 的可见条件互相独立，聚在一处才能一眼对照。
 *
 * 「后端」在 header 里只有一种形态：已建会话的只读后缀（「AI 助手 · Pi」）。它
 * 不是按钮——`agent_kind` 建会话时定死，换不了。新对话态 header **不含**任何后端
 * 控件：选谁由输入区的 AnswerAgentMenu 一处承担（勾的第一个同时成为新会话归属，
 * 见 store/turn.ts）。两处都能选就是「逻辑重复」，且两处一旦不一致，用户看到的
 * 本轮参与方与实际发生的会话归属就是两回事。
 *
 * 状态与动作都由宿主传入，只有一处例外：已建会话的后端名要取**显示名**（`Pi` /
 * `DeepSeek Harness`），清单在 store 里。两个宿主（抽屉 CopilotPanel / 独立页
 * AssistantPage）都只传 kind，为一个标题后缀把 label 串过两层 props 只会让
 * 宿主各存一份派生值，故这里直接读同一个 slice（不是第二份数据源：清单只有
 * store 一份，selector 拿到的还是同一个数组引用）。
 *
 * 「历史」按钮把 UI 动作审计台账（`GET /agent/ui-actions`）摆到律师眼前：AI 动过
 * 什么、他批还是拒了、页面报的成功在库里是否真的发生了。台账按律师查、与当前
 * 会话无关，所以打开状态是本组件的本地 state（没有第二个读者）；面板也只在
 * 打开后挂载——没打开就不发请求。
 */

import { useState } from 'react'
import { Columns2, FolderTree, History, Maximize2, Minimize2, PanelLeftClose, PanelLeftOpen, Plus, Sparkles, SquareStack, X } from 'lucide-react'

import { useCopilot } from '../store'
import { findBackend } from '../store/backends'
import type { CopilotContext } from '../types'
import { UiActionHistory } from './UiActionHistory'

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
  /**
   * 当前会话的后端 kind；null = 还没有会话。
   *
   * 有会话时它就是标题后面的弱化后缀（`AI 助手 · antigravity`）——后端名必须
   * **看得见**，不能只放 `title`。新对话态这里既没有后缀也没有下拉：新会话用谁由
   * 输入区的 AnswerAgentMenu 决定（唯一入口）。
   */
  currentAgentKind: string | null
  onNewSession: () => void
  /** 收起（仅抽屉有）：缺省时不渲染关闭钮 */
  onClose?: () => void
  /**
   * 跳到全屏助手页（`/assistant`）；缺省时不渲染「全屏」钮。
   *
   * 只有**抽屉**传它：独立页自己就是全屏，再放一个「全屏」钮没有意义。
   *
   * 为什么要这个钮：顶栏左侧导航里也有一个叫「AI 助手」的入口，但那是跳到
   * 新页面；而顶栏右侧同名按钮开的是抽屉。两个入口同名，用户点了右边的
   * 就以为「跳转坏了」（真实反馈）。在抽屉里直接给一个「全屏」，比让用户
   * 去猜哪个「AI 助手」才是页面直观得多。
   */
  onExpand?: () => void
  /**
   * 退出全屏助手页（回到进入前的页面）；只有**独立页**传它。
   *
   * 为什么必须有它：全屏页没有导航栏入口可以「点回去」，不给出口用户就被困在
   * 那一页里（真实反馈：全屏之后不知道怎么缩回去）。
   *
   * 用**带文字**的按钮而不是一颗小图标：上一版只给了图标入口，用户没找到。
   * 出口这种「后悔药」宁愿占点地方，也要一眼看得见。
   */
  onExitFullscreen?: () => void
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
  onExpand,
  onExitFullscreen,
}: CopilotHeaderProps) {
  const backends = useCopilot((s) => s.backends)
  const [historyOpen, setHistoryOpen] = useState(false)
  // 已有会话的后端名：清单没到（或拉取失败）时退回 kind 原文，宁可显示 `pi` 也不空着
  const sessionAgentLabel = currentAgentKind
    ? (findBackend(backends, currentAgentKind)?.label ?? currentAgentKind)
    : null

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
      <span className="flex min-w-0 flex-1 items-baseline gap-1 px-0.5">
        <span className="min-w-0 truncate text-[13px] font-semibold text-foreground">
          {context ? `AI 助手 · ${context.title}` : currentTitle || 'AI 助手'}
        </span>
        {/* 会话级后端名：只说事实（谁是本会话的后端），弱化到与标题同一行的后缀。
            不是按钮——后端在建会话时定死，「换」这个动作在这里没有落点（唯一的
            出口是「新对话」，其 tooltip 说明了原因）。 */}
        {sessionAgentLabel && (
          <span className="max-w-28 flex-none truncate text-[11px] font-normal text-muted-foreground">
            · {sessionAgentLabel}
          </span>
        )}
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
        onClick={() => setHistoryOpen(true)}
        aria-label="AI 操作历史"
        title="查看 AI 需要审批的操作记录：谁批的、页面报的成功是否真的在库里发生"
      >
        <History className="h-3.5 w-3.5" />
        历史
      </button>
      <button
        type="button"
        className="flex h-7 flex-none items-center gap-1 rounded-[8px] px-2 text-[12.5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        onClick={onNewSession}
        title="需要换后端请新建对话——后端在建会话时确定，中途更换会丢失上下文"
      >
        <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
        新对话
      </button>
      {historyOpen && <UiActionHistory open onOpenChange={setHistoryOpen} />}
      {onExitFullscreen && (
        <button
          type="button"
          className="flex h-7 flex-none items-center gap-1 rounded-[8px] px-2 text-[12px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={onExitFullscreen}
          aria-label="退出全屏"
          title="退出全屏，回到进入前的页面"
        >
          <Minimize2 className="h-3.5 w-3.5" />
          退出全屏
        </button>
      )}
      {onExpand && (
        <button
          type="button"
          className="flex h-7 w-7 flex-none items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={onExpand}
          aria-label="在全屏窗口中打开 AI 助手"
          title="全屏打开（多 agent 并排时更宽敞）"
        >
          <Maximize2 className="h-4 w-4" />
        </button>
      )}
      {onClose && (
        <button
          type="button"
          className="flex h-7 w-7 flex-none items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={onClose}
          aria-label="收起 AI 助手"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </header>
  )
}
