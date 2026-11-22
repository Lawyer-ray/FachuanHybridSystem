/**
 * 一轮流式对话的 store 更新处理器（**装配层**）。
 *
 * createTurnHandlers 返回 { handlers, finishAssistant }：
 * - handlers 喂给 streaming.consumeAgentStream，把 SSE 事件翻译成 Zustand 状态更新
 * - finishAssistant 收尾助手气泡（流读尽与 done 双路径都要能调，幂等）
 *
 * 处理器按关注点分在同目录 `handlers/`（本文件只负责建上下文并拼装）：
 * - content-handlers.ts     正文/思考/引用（写消息）
 * - tool-handlers.ts        工具行状态机 + `rewrite_folder_file` 参数缓存与广播
 * - lane-lifecycle.ts       用量记账、压缩/排队、降级与失败、每栏收尾判定
 * - approval-question.ts    审批卡、模型反问、排队名次、压缩阶段
 * - 纯计算在 `domain/lane-stats.ts`（用量/采样）与 `domain/tool-rewrite.ts`（改写参数）
 *
 * store 的读写一律由调用方注入（`set` / `get`）：本文件不 import store，否则
 * store/turn → turn-handlers → store 会成模块级环（初始化顺序稍有不同就会读到
 * undefined 的切片）。
 */

import type { GetState, SetState } from './store/slice'
import type { StreamHandlers } from './streaming'
import type { CopilotState } from './types'
import { createApprovalQuestionHandlers } from './handlers/approval-question'
import type { TurnHandlerContext } from './handlers/context'
import { createContentHandlers } from './handlers/content-handlers'
import { createLaneLifecycleHandlers } from './handlers/lane-lifecycle'
import { createToolHandlers } from './handlers/tool-handlers'

type CopilotSet = SetState<CopilotState>
type CopilotGet = GetState<CopilotState>

/**
 * `assistantFor`：事件的 agent kind → 该写进哪条 assistant 气泡的 id。
 *
 * 键是 `agent`（`pi` / `dsh`），特殊键 `''` 是兜底（单后端轮次 / 事件缺 agent）。
 * 由 store 在开流时按「本轮有哪些栏」建好，闭包里只读不写。
 */
export type AssistantRoute = (kind: string) => string

export function createTurnHandlers(
  defaultAssistantId: string,
  set: CopilotSet,
  /** 读最新 state（`useCopilot.getState` 注入）：收尾判定与跨 slice 动作要用 */
  get: CopilotGet,
  assistantFor: AssistantRoute = () => defaultAssistantId,
  /** 本轮选了几栏（>1 = 多答）。注意它只表达「律师想跑几栏」，
   *  **不能**用来判「事件该怎么路由」——见下方 targetOf。错误行只在多栏时才标来源：
   *  单后端时多加一个「pi：」前缀会改变律师已经习惯的文案，而它并不带来任何
   *  区分信息。 */
  columnCount = 1,
): {
  handlers: StreamHandlers
  finishAssistant: () => void
} {
  /**
   * 这一帧该写进哪条气泡。
   *
   * 多栏时 `origin.kind` 是精确的，但**按栏清单判断，不按 columnCount 判断**：
   * 后端可能降级（aux 席位满 → 只跑主后端并收窄 agents），也可能某个 kind 不在
   * 清单里。这两种情况下 `assistantFor` 会回落到默认气泡——单栏轮次里事件带的
   * `agent` 是后端自己的 kind（`pi` / `dsh` / `openai-agents`），而单栏气泡没有
   * 登记在任何 kind 名下（见 store/turn.ts：只有多栏才建 assistantByAgent）。
   * 一律走 `assistantFor` 让「路由表怎么建的就怎么查」，两处只有一份真相。
   */
  const ctx: TurnHandlerContext = {
    set,
    get,
    targetOf: (kind) => assistantFor(kind),
    columnCount,
  }

  const lane = createLaneLifecycleHandlers(ctx)

  return {
    handlers: {
      ...createContentHandlers(ctx),
      ...createToolHandlers(ctx),
      ...lane.handlers,
      ...createApprovalQuestionHandlers(ctx),
    },
    finishAssistant: lane.finishAssistant,
  }
}
