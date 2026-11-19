/**
 * 转录消息 id 的解析（纯函数）。
 *
 * 两种 id 并存是刻意的：
 * - `db-<消息主键>`：历史回放（服务端已落库，可评分、可翻页锚点）；
 * - `local-<递增>`：本轮实时流式气泡（还没落库，**没有**主键）。
 *
 * 之前调用方直接 `Number(id.slice(3))` 反推主键：对 `db-12` 侥幸成立，对
 * `local-7` 得到 `NaN` 然后一路传进 `rateMessage` / 评分请求——界面上按钮可点、
 * 点了没反应（`404/NaN` 在后端静默失败）。把判定收在这一处，UI 才不会「假可用」。
 */

import type { ChatMessage } from '../types'

/** 历史分页页大小（与后端 `list_messages` 的默认 limit 同口径） */
export const HISTORY_PAGE_SIZE = 200

/** 消息主键：`db-12` → 12；`local-3` / 未知前缀 → null */
export function parseMessageId(id: string): number | null {
  if (!id.startsWith('db-')) return null
  const raw = id.slice(3)
  if (!/^\d+$/.test(raw)) return null
  const n = Number(raw)
  return Number.isSafeInteger(n) && n > 0 ? n : null
}

/**
 * 这条消息能否评分（点赞/点踩）。
 *
 * 判据是「有没有落库主键」：`serverId` 优先（历史回放显式带上），否则从
 * `db-` id 反推。实时气泡在落库前恒为 false——UI 该置灰并给出原因，
 * 而不是让律师点了没反应。
 */
export function ratableMessageId(message: Pick<ChatMessage, 'id' | 'serverId'>): number | null {
  if (typeof message.serverId === 'number' && message.serverId > 0) return message.serverId
  return parseMessageId(message.id)
}

/** 首条已落库消息的主键（翻页游标：取它之前那一页） */
export function oldestDbId(messages: readonly Pick<ChatMessage, 'id' | 'serverId'>[]): number | null {
  for (const m of messages) {
    const id = ratableMessageId(m)
    if (id !== null) return id
  }
  return null
}
