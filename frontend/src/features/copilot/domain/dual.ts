/**
 * 同题双答（dual）的分流与展示口径。
 *
 * 后端 `stream_dual` 把两个 agent 的事件**按到达顺序交错**推给前端，每个事件带
 * `agent`（谁产的）与 `run_id`（哪一轮的哪一栏）。本模块只做两件纯变换：
 *
 * 1. **分流键归一**：事件 → 该追加到哪条 assistant 消息（见 {@link agentOf}）；
 * 2. **展示标签**：kind → 中文名（见 {@link agentLabel}）。
 *
 * 为什么放在 domain 而不是组件里：分流的正确性（同一轮两栏各归各家）必须能在
 * node 环境直接单测，不能只靠渲染 DOM 去间接验——DOM 断言失败时看不清是
 * 「分错了栏」还是「样式没出来」。
 */

import type { ChatMessage } from '../types'

/** 转录项：一条消息，或一轮里连续的若干条 assistant（双答时两条） */
export interface AnswerGroup {
  answers: ChatMessage[]
}

/** 空串 / 未标注一律当 pi：引入双答之前本系统只有 pi 在跑（见后端字段注释） */
export const DEFAULT_AGENT_KIND = 'pi'

/**
 * 事件该归到哪个 agent。
 *
 * 绝大多数事件带 `agent`；缺失时（旧后端 / 早于本字段的事件）回落到会话级口径
 * pi——**不能**回落到「当前主后端」，否则双答里主后端的事件会被同时写进两条。
 */
export function agentOf(event: object): string {
  // 事件类型是判别联合，多数成员没有 `agent` 字段（delta / thinking / usage…）。
  // 这里用属性探测而不是要求每个成员都声明它：契约里 `agent` 是「转发方补齐」的
  // 可选字段，让联合成员逐个声明只会变出两份定义。
  const agent = (event as { agent?: string }).agent
  return agent || DEFAULT_AGENT_KIND
}

/** 事件里的 `run_id`（缺省空串）；前端只做透传与日志，不解析它的内部结构 */
export function runIdOf(event: object): string {
  return (event as { run_id?: string }).run_id ?? ''
}

/** kind → 栏标签（只列需要中文名的；未知 kind 直接显示 kind 自身） */
const AGENT_LABELS: Record<string, string> = {
  pi: 'Pi',
  dsh: 'DeepSeek Harness',
}

export function agentLabel(kind: string): string {
  return AGENT_LABELS[kind] ?? kind
}

/**
 * 把转录切成「渲染项」：连续的 assistant 合成一组，其余消息各自成组。
 *
 * 为什么按**连续**而不是「按轮次键」：转录里没有轮次 id（后端消息表也不存），
 * 两栏回答确实是相邻写入的（同一轮、同一时刻）。连续性判据不需要额外字段，
 * 也不会因为历史数据缺字段而失效——代价是「用户消息 + 单个 assistant + 另一个
 * 单 assistant」这种不连续排列不会被当成双答，那本来也不是双答（双答必相邻）。
 *
 * 单条 assistant 也返回长度为 1 的组：调用方用一个形状处理，不必分两条路径。
 */
export function groupAnswerRuns(messages: ChatMessage[]): AnswerGroup[] {
  const groups: AnswerGroup[] = []
  for (const message of messages) {
    const last = groups[groups.length - 1]
    const mergeable = message.role === 'assistant' && last?.answers[0]?.role === 'assistant'
    if (mergeable) last.answers.push(message)
    else groups.push({ answers: [message] })
  }
  return groups
}
