/**
 * 处理器共用的注入面：store 读写、气泡路由与「本轮几栏」。
 *
 * 为什么单独一个类型：`turn-handlers.ts` 只剩装配，每个处理器工厂（正文 / 工具 /
 * 用量与收尾 / 审批与提问）都要同样的四样东西。用一份契约而不是四个位置参数，
 * 加一样共享能力时不会去改四个签名。
 */

import type { GetState, SetState } from '../store/slice'
import type { CopilotState } from '../types'

export interface TurnHandlerContext {
  /** 写 store（真身是 `useCopilot.setState`） */
  set: SetState<CopilotState>
  /** 读最新 state（真身是 `useCopilot.getState`）：收尾判定与跨 slice 动作要用 */
  get: GetState<CopilotState>
  /**
   * 事件的 agent kind → 该写进哪条 assistant 气泡的 id。
   *
   * 路由表由 store 在开流时按「本轮有哪些栏」建好，这里只查不建——两处只有一份真相。
   */
  targetOf: (kind: string) => string
  /**
   * 本轮选了几栏（>1 = 多答）。
   *
   * 它只表达「律师想跑几栏」，**不能**用来判「事件该怎么路由」（见 targetOf）；
   * 只用于错误行的来源前缀与审批卡上的栏标签。
   */
  columnCount: number
}
