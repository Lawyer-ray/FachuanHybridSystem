/**
 * store slice：本轮跑哪几个 agent、各用哪个模型（多答＝一轮并排 1~MAX_ANSWERS 栏）。
 *
 * 为什么选择放进 store 而不是组件本地 state：`send` 在 `store/turn.ts` 里开流前
 * 就要知道「本轮有几栏、每栏哪个模型」——建气泡、事件路由、请求体全依赖它，而
 * 这些都发生在用户敲下回车那一刻，不是组件能拦的路由。
 *
 * ## 与「会话后端」是两回事
 *
 * 会话的 `agent_kind` 建完不可更换（上下文归后端自己管）。`selectedAgentKind`
 * （`store/backends.ts`）是「一个都不勾」时的会话归属回退值；勾了 agent 时归属
 * 由本轮选择推导（见 `store/turn.ts`）。本 slice 的 `answerAgents` 决定**这一轮问
 * 哪几家**，可以逐轮改：多答是「同一问题拿几份意见」，不是「换脑子」。
 *
 * ## 模型与勾选分开存
 *
 * `answerModels` 只记「律师显式指定过的模型」。后端清单还没到（`models` 为空）时
 * 依然可以记：真正决定发不发 `model` 的是 `store/turn.ts` 的
 * `resolveAnswerSpecs`——所以清单短暂缺失不会把已选的模型吞掉。
 *
 * ## 上限
 *
 * {@link MAX_ANSWERS} 与后端同口径；超出的选择在这里就被拒掉（UI 也会置灰），
 * 否则请求会在后端 400，而那时用户已经敲了回车。
 */

import { MAX_ANSWERS } from '../domain'
import type { CopilotState } from '../types'
import type { Slice } from './slice'

export type AnswersSlice = Pick<
  CopilotState,
  'answerAgents' | 'toggleAnswerAgent' | 'answerModels' | 'setAnswerModel'
>

export const createAnswersSlice: Slice<AnswersSlice> = (set, get) => ({
  answerAgents: [],
  answerModels: {},

  toggleAnswerAgent: (kind) => {
    const current = get().answerAgents
    if (current.includes(kind)) {
      // 取消：从清单移除即回到「未选择」（`[]` = 用会话默认后端单跑）
      set({ answerAgents: current.filter((k) => k !== kind) })
      return
    }
    // 到顶后忽略新增（UI 已置灰；键盘/程序路径也不该放行，否则后端 400）
    if (current.length >= MAX_ANSWERS) return
    set({ answerAgents: [...current, kind] })
  },

  setAnswerModel: (kind, model) => {
    const current = get().answerModels
    // 幂等：同一个模型重复选不写状态（菜单重渲染时不制造无意义的新对象）
    if ((current[kind] ?? '') === model) return
    const next = { ...current }
    // 空串 = 取消指定：删键而不是存空串，`resolveAnswerSpecs` 据此省略 `model` 字段
    if (model) next[kind] = model
    else delete next[kind]
    set({ answerModels: next })
  },
})
