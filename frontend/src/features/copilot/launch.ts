/**
 * Copilot 启动入口：供其他 feature 打开 AI 助手面板（可选携带业务上下文）。
 *
 * **为什么是独立入口而不是从 index.ts re-export**：index.ts 静态引着
 * CopilotPanel（App.tsx 靠 `import('@/features/copilot')` 把整个 copilot 域
 * 拆成懒 chunk）。任何 feature 若从 index 引 openCopilot，会把面板及其依赖
 * （react-markdown 等）拖进使用方 chunk，破坏懒加载边界。本文件不 import
 * store / 组件，只引 domain 纯函数（type-only + 无 React 依赖），跨域引入
 * 它代价为零——这是有意的架构豁免，勿改回 index。
 *
 * 链路：openCopilot(ctx) 记下 pending 上下文 → 派发 window 事件 →
 * AppShell 收到开面板；CopilotPanel 挂载/已挂载时读取事件与 pending，
 * 把上下文写进 store（enterContext）。面板 chunk 未加载的竞态由
 * takePendingLaunchContext 兜底（挂载后即取走）。
 */

// domain 是纯函数模块（无 React/store 依赖），引它不破坏本文件的懒 chunk
// 边界（见文件头注释）；类型均为 type-only，编译期擦除。
import { normalizeSelectionText } from './domain'
import type { FileRewriteSignal } from './domain'
import type { SelectionQuote } from './types'

export interface CopilotLaunchContext {
  /** 业务入口：case（案件内）/ contract（合同/委托内） */
  origin: 'case' | 'contract'
  /** 对应业务 id（案件 id 或合同 id） */
  refId: number
  /** 展示名（面板头部 chip 用，如客户/委托名） */
  title: string
}

export const COPILOT_LAUNCH_EVENT = 'copilot:launch'

let pending: CopilotLaunchContext | null = null

/** 打开 AI 助手面板；携带上下文时面板进入「业务内会话」模式 */
export function openCopilot(context?: CopilotLaunchContext): void {
  pending = context ?? null
  window.dispatchEvent(new CustomEvent<CopilotLaunchContext | null>(COPILOT_LAUNCH_EVENT, { detail: context ?? null }))
}

/** 面板挂载时取走尚未消费的启动上下文（chunk 加载竞态的兜底），取后即清 */
export function takePendingLaunchContext(): CopilotLaunchContext | null {
  const ctx = pending
  pending = null
  return ctx
}

/**
 * 选区预填事件：把编辑器里的选区（含前后文）塞进 AI 输入框。
 *
 * **为什么不走 store**：Composer 的输入框文本是组件本地 state（用户正在打字
 * 的草稿，被流式重渲染打断就丢字），放进 store 会变成「受控状态」，
 * 每次 keystroke 都过一遍全局订阅。这里只需要一次性的「塞一段文字进去」，
 * 自定义事件足够，且 Composer 不在场时自然无副作用。
 */
export const COPILOT_PREFILL_EVENT = 'copilot:prefill'

export interface CopilotPrefillDetail {
  /** 要写入输入框的文本（通常是一句带引用的指令模板） */
  text: string
}

/** 把一段文本塞进 AI 助手输入框（面板未打开时先打开）
 *
 * 传空字符串是合法的：只把面板打开、不写任何内容（用于「按钮点下去就要有反应」）。
 */
export function prefillCopilot(text: string, context?: CopilotLaunchContext): void {
  openCopilot(context)
  if (!text.trim()) return
  // 面板是懒加载 chunk：刚挂载时 Composer 还没订阅事件，下一帧再发
  window.setTimeout(() => {
    window.dispatchEvent(new CustomEvent<CopilotPrefillDetail>(COPILOT_PREFILL_EVENT, { detail: { text } }))
  }, 120)
}

/**
 * 框选引用事件（豆包式引用）：编辑器里选中一段文本后，引用挂到输入框上方
 * 的引用卡（store 的 pendingQuote），输入框保持空白供律师自由提问——
 * 不是把「请按我的要求改写…」模板灌进输入框（旧做法，律师实际不想被打草稿）。
 *
 * 与 prefill 的关键差异：引用是**结构化状态**（随消息出站、回放成卡），
 * 必须进 store；而事件只是「面板可能还没挂载」时的传输手段。挂载竞态由
 * takePendingQuote 兜底（Composer 挂载后即取走）。
 */
export const COPILOT_QUOTE_EVENT = 'copilot:selection-quote'

let pendingSelectionQuote: SelectionQuote | null = null

/** 打开助手面板并把一段选区设为输入框上方的引用卡 */
export function quoteCopilot(quote: SelectionQuote, context?: CopilotLaunchContext): void {
  // 展示侧先做归一（换行压平、限长）；出站块的整形在 domain.buildSelectionQuoteBlock
  pendingSelectionQuote = { ...quote, text: normalizeSelectionText(quote.text) }
  openCopilot(context)
  window.dispatchEvent(new CustomEvent<SelectionQuote>(COPILOT_QUOTE_EVENT, { detail: pendingSelectionQuote }))
}

/** Composer 挂载时取走尚未消费的选区引用（chunk 加载竞态的兜底），取后即清 */
export function takePendingQuote(): SelectionQuote | null {
  const q = pendingSelectionQuote
  pendingSelectionQuote = null
  return q
}

/** 清掉未消费的选区引用（消费方在事件/兜底两条路径取走时调用，防重复挂卡） */
export function clearPendingQuote(): void {
  pendingSelectionQuote = null
}

/**
 * 「AI 已把修订写回文件夹文件」事件：流式处理器（turn-handlers）在
 * tool_result 里识别到 rewrite_folder_file 落盘成功时派发，workbench 的
 * 编辑器刷新钩子（use-rewrite-refresh）消费——正在打开该文件的画布据此
 * 重签配置、换 document key，DS 才会重新拉已覆写的文件（修订痕迹可见）。
 *
 * 与 quote/prefill 的差异：这是 **copilot → 其它 feature** 的单向广播，
 * 没有 pending 兜底（消费方不在场 = 没有画布需要刷新，丢了反而正确）。
 */
export const FILE_REWRITTEN_EVENT = 'fachuan:file-rewritten'

export type FileRewrittenDetail = FileRewriteSignal
