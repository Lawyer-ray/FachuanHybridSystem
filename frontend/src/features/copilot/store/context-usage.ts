/**
 * store slice：上下文水位与消息反馈。
 *
 * 水位（contextUsage）的写入口只有两个：done 事件（turn-handlers）与这里的
 * stats/compact 回填；拉不到一律静默——水位是增强信息，缺失只是不显示，
 * 不得因此给律师报错。压缩走 /compact（服务端 compaction），429 单独给忙提示。
 */

import { HTTPError } from 'ky'

import * as copilotApi from '../api'
import { ratableMessageId } from '../domain'
import type { ChatMessage, CopilotState } from '../types'
import type { Slice } from './slice'

export type ContextUsageSlice = Pick<
  CopilotState,
  'setContextUsage' | 'refreshContextUsage' | 'compactContext' | 'rateMessage'
>

export const createContextUsageSlice: Slice<ContextUsageSlice> = (set, get) => ({
  setContextUsage: (used, total) => {
    set({ contextUsage: { used, total } })
  },

  refreshContextUsage: async () => {
    const id = get().sessionId
    if (!id) return
    try {
      const stats = await copilotApi.fetchSessionStats(id)
      // 等待期间可能切走：只回填仍是当前会话的水位
      if (get().sessionId === id) {
        set({ contextUsage: { used: stats.context_used_tokens, total: stats.context_total_tokens } })
      }
    } catch {
      // 静默：水位是增强信息，拉不到只是不显示
    }
  },

  compactContext: async () => {
    const id = get().sessionId
    if (!id || get().compacting || get().streaming) return
    set({ compacting: true, lastError: null })
    try {
      const receipt = await copilotApi.compactSession(id)
      set({ contextUsage: { used: receipt.context_used_tokens, total: receipt.context_total_tokens } })
      if (!receipt.compacted) set({ lastError: '会话还没有对话历史，无需压缩' })
    } catch (err) {
      const status = err instanceof HTTPError ? err.response.status : 0
      set({ lastError: status === 429 ? '当前使用人数较多，请稍后再试' : '压缩失败，请稍后再试' })
    } finally {
      set({ compacting: false })
    }
  },

  rateMessage: async (messageId, rating) => {
    // 按**落库主键**匹配，不拼 `db-${id}` 字符串：拼串只对历史气泡成立，
    // 实时气泡（local-*）会永远匹配不到，点了没任何反应。
    // ratableMessageId 兼容两种来源：显式 serverId，或 `db-` 前缀反推。
    const matches = (m: ChatMessage) => ratableMessageId(m) === messageId
    const prev = get().messages.find((m) => matches(m))?.rating
    const apply = (r?: 'up' | 'down') =>
      set((s) => ({
        messages: s.messages.map((m) => (matches(m) ? { ...m, rating: r } : m)),
      }))
    apply(rating === 'none' ? undefined : rating)
    try {
      await copilotApi.rateMessage(messageId, rating)
    } catch {
      apply(prev) // 失败回滚
    }
  },
})
