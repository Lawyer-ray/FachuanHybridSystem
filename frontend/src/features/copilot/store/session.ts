/**
 * store slice：会话生命周期（切换 / 进入业务范围 / 历史回放与分页）。
 *
 * 只做状态编排——SSE 帧消费在 streaming.ts、轮处理器在 turn-handlers.ts、
 * localStorage 在 persistence.ts、crossfade 在 transitions.ts。
 */

import * as copilotApi from '../api'
import { historyToMessages } from '../domain'
import { storeSession } from '../persistence'
import { withViewTransition } from '../transitions'
import type { CopilotState } from '../types'
import { bumpSessionEpoch, currentSessionEpoch } from './session-epoch'
import type { Slice } from './slice'

export type SessionSlice = Pick<
  CopilotState,
  'enterContext' | 'exitContext' | 'switchSession' | 'refreshHistory' | 'loadOlderHistory'
>

export const createSessionSlice: Slice<SessionSlice> = (set, get) => ({
  enterContext: async (context) => {
    // 幂等：已在同一业务范围（详情页每次数据刷新都会重进）不重置对话。
    // 页面进入时自动绑定（不再依赖用户点按钮）后，这条短路是必须的——
    // 否则任何一次 effect 重跑都会把用户正在进行的会话清成空白新对话。
    const cur = get().context
    if (cur?.origin === context.origin && cur.refId === context.refId) {
      if (cur.title !== context.title) set({ context })
      return
    }
    if (get().streaming) get().stop()
    set({ context })
    // 沿用该业务范围**最近**的会话（列表按 updated_at 降序，第一条即最近），
    // 没有历史会话才落空白新对话——「进项目 = 接着上次聊」，开新对话只能
    // 由律师主动点「新对话」。拉取失败按无历史处理，不阻塞进页。
    const epochAtFetch = currentSessionEpoch()
    let resumeId: string | null
    try {
      const latest = await copilotApi.listSessions(1, { origin: context.origin, refId: context.refId })
      resumeId = latest[0]?.session_id ?? null
    } catch {
      resumeId = null
    }
    // await 期间律师动过会话（点新对话/切会话/发消息建会话，见 sessionEpoch）
    // 或范围又被切走（快速跳页）：用户动作优先，迟到的自动恢复不得覆盖。
    const now = get().context
    if (now?.origin !== context.origin || now?.refId !== context.refId) return
    if (currentSessionEpoch() !== epochAtFetch) return
    await get().switchSession(resumeId)
  },

  exitContext: async () => {
    if (get().streaming) get().stop()
    set({ context: null })
    await get().switchSession(null)
  },

  switchSession: async (id) => {
    bumpSessionEpoch()
    const prev = get()
    // 同会话且**视图已就绪**才跳过：不重复拉取、不播切换动画
    // （stop 后的重拉 streaming 仍为 true，放行）。
    //
    // 原条件 `(id !== null || prev.messages.length === 0)` 在 id 非空时恒真，
    // 等于「同 id 就跳过」——刷新页面后 store 从 localStorage 恢复了 sessionId
    // 但 messages 还是空数组，面板挂载时调 switchSession(同一个 id) 被直接
    // return，历史永远不加载，表现为「侧栏选中着会话、主区域却是欢迎页，
    // 发了消息才突然出现旧内容」。就绪的判据是「已有正文」而不是「id 相同」。
    const hasView = prev.messages.length > 0 || prev.loadingHistory
    if (id === prev.sessionId && !prev.streaming && (id === null || hasView)) return
    get().stop()
    withViewTransition(() => {
      set({ sessionId: id, messages: [], approvals: [], lastError: null, loadingHistory: id !== null, queuePosition: null, queuedSteers: [], contextUsage: { used: null, total: null } })
    })
    storeSession(id)
    if (!id) return
    // 会话打开即拉一次水位（done 事件会在每轮结束后刷新）
    void get().refreshContextUsage()
    try {
      const rows = await copilotApi.fetchHistory(id)
      // 等待期间用户可能又切走了：只回填仍是当前会话的结果
      if (get().sessionId === id) {
        withViewTransition(() => {
          set({ messages: historyToMessages(rows), loadingHistory: false, noMoreHistory: rows.length < 200 })
        })
      }
    } catch {
      if (get().sessionId === id) {
        withViewTransition(() => {
          set({ lastError: '加载会话历史失败', loadingHistory: false })
        })
      }
    }
  },

  refreshHistory: async () => {
    const id = get().sessionId
    if (!id || get().streaming) return
    try {
      const rows = await copilotApi.fetchHistory(id)
      if (get().sessionId === id) {
        withViewTransition(() => {
          set({ messages: historyToMessages(rows) })
        })
      }
    } catch {
      // 静默：轮询刷新失败不影响现有转录
    }
  },

  loadOlderHistory: async () => {
    const { sessionId, messages, loadingHistory, streaming, noMoreHistory } = get()
    if (!sessionId || loadingHistory || streaming || noMoreHistory) return
    const oldest = messages.find((m) => m.id.startsWith('db-'))
    const beforeId = oldest ? Number(oldest.id.slice(3)) : undefined
    if (!beforeId) {
      set({ noMoreHistory: true })
      return
    }
    set({ loadingOlder: true })
    try {
      const older = await copilotApi.fetchHistory(sessionId, 200, beforeId)
      if (older.length === 0) {
        set({ noMoreHistory: true })
        return
      }
      set((s) => ({
        messages: [...historyToMessages(older), ...s.messages],
        noMoreHistory: older.length < 200,
      }))
    } catch {
      /* 静默：翻页失败不打扰当前对话 */
    } finally {
      set({ loadingOlder: false })
    }
  },
})
