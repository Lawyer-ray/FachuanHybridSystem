/**
 * Copilot 启动入口：供其他 feature 打开 AI 助手面板（可选携带业务上下文）。
 *
 * **为什么是独立入口而不是从 index.ts re-export**：index.ts 静态引着
 * CopilotPanel（App.tsx 靠 `import('@/features/copilot')` 把整个 copilot 域
 * 拆成懒 chunk）。任何 feature 若从 index 引 openCopilot，会把面板及其依赖
 * （react-markdown 等）拖进使用方 chunk，破坏懒加载边界。本文件零依赖、
 * 不 import store，跨域引入它代价为零——这是有意的架构豁免，勿改回 index。
 *
 * 链路：openCopilot(ctx) 记下 pending 上下文 → 派发 window 事件 →
 * AppShell 收到开面板；CopilotPanel 挂载/已挂载时读取事件与 pending，
 * 把上下文写进 store（enterContext）。面板 chunk 未加载的竞态由
 * takePendingLaunchContext 兜底（挂载后即取走）。
 */

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
