/**
 * 轮次大纲：把转录切成「一轮 = 一条提问 + 其后的回答」（长会话导航的数据源）。
 *
 * 基于**已加载窗口**：`loadOlderHistory` 之前的部分不在这里——大纲与转录视图
 * 同源，翻到更早那一页后重新 build 即可，不是缺陷。
 */

import type { ChatMessage } from '../types'
import { DEFAULT_AGENT_KIND } from './dual'

/** 大纲一项（TurnRail 的数据源） */
export interface TurnOutline {
  /** 1 起的轮号（按已加载窗口内顺序） */
  turn: number
  /** 该轮用户提问的消息 id —— 宿主点击跳转的锚点 */
  promptId: string
  /** 该轮第一条有正文的回答 id（整轮失败 / 只有工具时缺省） */
  answerId?: string
  /** 用户问题前 40 字（换行归一为空格） */
  preview: string
  /** 提问时刻（ms）；无时间戳的历史行为 undefined */
  at?: number
  /** 本轮实际产出的 agent（按首次出现顺序；旧数据按 pi） */
  agents: string[]
}

/** 预览长度上限（超出补省略号） */
const PREVIEW_MAX = 40

/** 用户问题 → 单行预览（中文按 code point 数） */
function previewOf(content: string): string {
  const chars = [...content.replace(/\s+/g, ' ').trim()]
  return chars.length > PREVIEW_MAX ? `${chars.slice(0, PREVIEW_MAX).join('')}…` : chars.join('')
}

export function buildTurnOutline(messages: ChatMessage[]): TurnOutline[] {
  const outline: TurnOutline[] = []
  for (const message of messages) {
    if (message.role === 'user') {
      outline.push({
        turn: outline.length + 1,
        promptId: message.id,
        preview: previewOf(message.content),
        ...(message.createdAt ? { at: message.createdAt } : {}),
        agents: [],
      })
      continue
    }
    const current = outline[outline.length - 1]
    // 窗口起点落在轮次中间：前面那几条没有可跳的提问，忽略（见文件头）
    if (!current || message.role !== 'assistant') continue
    if (!current.answerId && !(message.failed && !message.content.trim())) current.answerId = message.id
    const agent = message.agentKind || DEFAULT_AGENT_KIND
    if (!current.agents.includes(agent)) current.agents.push(agent)
  }
  return outline
}
