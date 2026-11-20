/**
 * store slice：会话生命周期（切换 / 进入业务范围 / 历史回放与分页）。
 *
 * 只做状态编排——SSE 帧消费在 streaming.ts、轮处理器在 turn-handlers.ts、
 * localStorage 在 persistence.ts、crossfade 在 transitions.ts。
 */

import * as copilotApi from '../api'
import { HISTORY_PAGE_SIZE, historyToMessages, oldestDbId } from '../domain'
import { storeSession } from '../persistence'
import { withViewTransition } from '../transitions'
import type { CopilotState } from '../types'
import { bumpSessionEpoch, currentSessionEpoch } from './session-epoch'
import type { Slice } from './slice'

export type SessionSlice = Pick<
  CopilotState,
  'enterContext' | 'exitContext' | 'switchSession' | 'refreshHistory' | 'loadOlderHistory'
>

/**
 * 「这一批是不是最后一页」——判断还有没有更早的历史，**唯一的判据**。
 *
 * 后端 `list_messages` 按 `created_at desc, id desc` 取 limit 条再反转成正序：
 * 不传 `before_id` 得到的是**最新一页**，传了得到的是该游标之前的一页。也就是说
 * 每个请求都是「切一刀取 limit 条」，所以只可能有两种结果——
 *
 * - 返回条数 == limit：被 limit 截断了，服务端大概率还有更早的（前端继续给按钮，
 *   点下去拿到 0 条时才真正收敛）；
 * - 返回条数 < limit：服务端手里的记录已经不够一页 ⟹ 这一刀切到了头，没有更早的。
 *
 * 这就是为什么判据必须写成「本批条数 < 页大小」，而不能写成任何**累计**口径
 * （比如「已加载总条数 < 页大小」或「本批条数 == 0」）：最新一页本身就可能是
 * 不足一页的短页，累计口径会把「一共只有 199 条」误判成「还能翻」。
 *
 * 三处调用点（首屏 / 轮询刷新 / 追加上一页）必须**全部**过这个函数，否则又会出现
 * 「某一处换了判据、按钮状态与实际不符」的老问题（见 store.session-history.test.ts
 * 的 100/199/200/201 / refreshHistory 用例）。
 */
function isLastHistoryPage(batch: readonly unknown[]): boolean {
  return batch.length < HISTORY_PAGE_SIZE
}

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
      // 切会话要清掉上一个会话的待答提问与草稿（与 approvals 同口径）：
      // 它们是「本会话的交互席位」，跨会话保留会让律师在 B 会话里回答 A 的问题
      set({
        sessionId: id,
        messages: [],
        approvals: [],
        pendingQuestions: [],
        questionDrafts: {},
        lastError: null,
        loadingHistory: id !== null,
        // 翻页下限**必须随会话一起清掉**：它是上一个会话的事实，不是新会话的。
        // 不清的话，在 A 会话翻到底（true）再切到 B，B 在历史回来之前（以及拉取
        // 失败时）会继承 A 的 true，按钮直接消失——用户看到的是「B 明明有更早的
        // 消息却加载不了」，刷新页面才恢复。
        noMoreHistory: false,
        queuePosition: null,
        queuedSteers: [],
        contextUsage: { used: null, total: null },
      })
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
          set({
            messages: historyToMessages(rows),
            loadingHistory: false,
            noMoreHistory: isLastHistoryPage(rows),
          })
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
          // 替换转录的同时**必须重算** noMoreHistory。原实现只换 messages，
          // 于是下面这个真实场景会把按钮永久藏起来：
          //   会话 250 条 → 首屏 200 条（false）→ 翻一页 50 条 → true（已到底）
          //   → 后台任务跑完触发 refreshHistory → 转录被换回「最新 200 条」，
          //     可 noMoreHistory 还是 true ⟹ 按钮不出，最早那 50 条再也翻不回来。
          // 替换后的转录是「最新一页」，就用同一把尺子（本批 < 页大小）重算。
          set({ messages: historyToMessages(rows), noMoreHistory: isLastHistoryPage(rows) })
        })
      }
    } catch {
      // 静默：轮询刷新失败不影响现有转录
    }
  },

  loadOlderHistory: async () => {
    const { sessionId, messages, loadingHistory, streaming, noMoreHistory } = get()
    if (!sessionId || loadingHistory || streaming || noMoreHistory) return
    // 游标 = 首条已落库消息的主键（实时气泡没有主键，跳过）
    const beforeId = oldestDbId(messages)
    if (!beforeId) {
      set({ noMoreHistory: true })
      return
    }
    set({ loadingOlder: true })
    try {
      const older = await copilotApi.fetchHistory(sessionId, HISTORY_PAGE_SIZE, beforeId)
      if (older.length === 0) {
        set({ noMoreHistory: true })
        return
      }
      set((s) => ({
        messages: [...historyToMessages(older), ...s.messages],
        // 追加上一页：到没到头只看**这一批**够不够一页（`older.length === 0` 的
        // 情况上面已提前返回，所以这里必然是 1..=页大小，`< 页大小` 即最后一页）。
        noMoreHistory: isLastHistoryPage(older),
      }))
    } catch {
      /* 静默：翻页失败不打扰当前对话 */
    } finally {
      set({ loadingOlder: false })
    }
  },
})
