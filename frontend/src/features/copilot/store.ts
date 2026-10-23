/**
 * Copilot 全局状态：转录、审批卡与流式收发。
 *
 * 流的生命周期归 store（模块级 Zustand）而非组件——收起面板不中断流；
 * 会话列表这类服务端状态走 react-query（SessionSidebar），不进本 store。
 * 领域编排在同域模块：streaming.ts（帧消费）、turn-handlers.ts（轮处理器）、
 * outgoing.ts（附件出站）、transitions.ts（视图过渡）、persistence.ts（会话
 * 持久化）、launch.ts（跨域启动入口）；状态形状见 types.ts 的 CopilotState。
 */

import { HTTPError } from 'ky'
import { create } from 'zustand'

import * as copilotApi from './api'
import {
  APPROVAL_OFFLINE_WINDOW_S,
  historyToMessages,
  isExpiredOfflineItem,
  nextLocalId,
  pendingItemToApproval,
  splitAttachmentFiles,
  splitPageHintLine,
  splitRefBlocks,
} from './domain'
import { resetUploadReceipts, uploadAttachmentsAndCompose } from './outgoing'
import { readStoredSession, storeSession } from './persistence'
import { consumeAgentStream } from './streaming'
import { createTurnHandlers } from './turn-handlers'
import { withViewTransition } from './transitions'
import type { CopilotState } from './types'

const EMPTY_STATS: CopilotState['turnStats'] = {
  firstDeltaAt: null,
  lastDeltaAt: null,
  doneAt: null,
  estTokens: 0,
  exactTokens: null,
  samples: [],
}

/** 在途流的中止句柄（模块级，随 store 生命周期） */
let controller: AbortController | null = null

export const useCopilot = create<CopilotState>((set, get) => ({
  sessionId: readStoredSession(),
  messages: [],
  approvals: [],
  streaming: false,
  loadingHistory: false,
  lastError: null,
  turnStats: EMPTY_STATS,
  queuePosition: null,
  queuedSteers: [],
  steering: false,
  context: null,
  pendingFiles: [],
  pendingRefs: [],
  pageHint: null,
  lastPageHintSent: null,
  uploadingAttachments: false,
  draggingFiles: false,
  noMoreHistory: false,
  loadingOlder: false,

  addAttachmentFiles: (files) => {
    const { accepted, rejected } = splitAttachmentFiles(Array.from(files))
    if (accepted.length === 0 && rejected.length === 0) return
    set((s) => ({
      pendingFiles: [...s.pendingFiles, ...accepted],
      draggingFiles: false,
      lastError: rejected.length > 0 ? `部分文件未添加：${rejected.join('；')}` : s.lastError,
    }))
  },

  removeAttachmentFile: (index) => {
    set((s) => ({ pendingFiles: s.pendingFiles.filter((_, i) => i !== index) }))
  },

  addFolderRef: (draft) => {
    set((s) => {
      if (s.pendingRefs.some((r) => r.contractId === draft.contractId && r.subpath === draft.subpath)) return s
      return { pendingRefs: [...s.pendingRefs, draft] }
    })
  },

  removeFolderRef: (index) => {
    set((s) => ({ pendingRefs: s.pendingRefs.filter((_, i) => i !== index) }))
  },

  setPageHint: (hint) => {
    if (get().pageHint === hint) return
    set({ pageHint: hint })
  },

  enterContext: async (context) => {
    if (get().streaming) get().stop()
    set({ context })
    await get().switchSession(null)
  },

  exitContext: async () => {
    if (get().streaming) get().stop()
    set({ context: null })
    await get().switchSession(null)
  },

  switchSession: async (id) => {
    const prev = get()
    // 同会话且视图已就绪：不重复拉取、不播切换动画（stop 后的重拉 streaming 仍为 true，放行）
    if (id === prev.sessionId && !prev.streaming && (id !== null || prev.messages.length === 0)) return
    get().stop()
    withViewTransition(() => {
      set({ sessionId: id, messages: [], approvals: [], lastError: null, loadingHistory: id !== null, queuePosition: null, queuedSteers: [] })
    })
    storeSession(id)
    if (!id) return
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

  send: async (text, onQueued) => {
    const trimmed = text.trim()
    if (!trimmed || get().streaming || get().uploadingAttachments) {
      onQueued?.(false)
      return
    }
    set({ lastError: null })

    // 通用模式（无业务 context）下注入「当前页面」锚点：页面变化后首条
    // 才注（历史不刷屏），模型可拿页面里的实体 id 用工具主动了解内容。
    // 业务范围内（详情页工作区/浮层 context 模式）不注——归属已经明确。
    const pre = get()
    let outgoingText = trimmed
    if (!pre.context && pre.pageHint && pre.pageHint !== pre.lastPageHintSent) {
      outgoingText = `[当前页面：${pre.pageHint}]\n${trimmed}`
      set({ lastPageHintSent: pre.pageHint })
    }

    // 本轮发送归属哪个会话：await 期间用户可能切会话/开新对话，
    // 迟到结果必须丢弃，否则会覆盖用户刚选中的会话并把消息推进去
    const startedSessionId = get().sessionId
    let sessionId = startedSessionId
    if (!sessionId) {
      try {
        sessionId = (await copilotApi.createSession('', get().context ?? undefined)).session_id
      } catch {
        set({ lastError: '创建会话失败，请稍后重试' })
        onQueued?.(false)
        return
      }
      // createSession 在途期间用户已切走：不占用新会话，也不污染当前视图
      if (get().sessionId !== startedSessionId) {
        onQueued?.(false)
        return
      }
      set({ sessionId })
      storeSession(sessionId)
    }

    // 附件先行上传（服务端存档拿引用 id），消息里附引用块——模型用
    // read_agent_attachment(id) 读正文，base64 不进上下文。任一失败则本轮
    // 不发、chips 保留可重试（outgoing 复用已成功回执，不重复上传）。
    const pendingFiles = get().pendingFiles
    const pendingRefs = get().pendingRefs
    if (pendingFiles.length > 0 || pendingRefs.length > 0) set({ uploadingAttachments: true })
    const outgoing = await uploadAttachmentsAndCompose(sessionId, outgoingText, pendingFiles, pendingRefs)
    set({ uploadingAttachments: false })
    if (outgoing === null) {
      set({ lastError: '附件/引用准备失败，请重试（已保留，重试不会重复上传）' })
      onQueued?.(false)
      return
    }
    // 附件上传在途期间用户可能切走：迟到结果丢弃（chips 保留，回执已缓存，
    // 下次发送不重复上传），不把消息推进新选中的会话
    if (get().sessionId !== sessionId) {
      onQueued?.(false)
      return
    }
    if (pendingFiles.length > 0 || pendingRefs.length > 0) set({ pendingFiles: [], pendingRefs: [] })
    const composed = outgoing.composed

    const assistantId = nextLocalId()
    // 与历史回放同一解析：本地即时渲染也把页面锚点/引用块还原成 chip，两侧不漂移
    const { pageHint, body: noHint } = splitPageHintLine(composed)
    const { refs, body } = splitRefBlocks(noHint)
    set((s) => ({
      messages: [
        ...s.messages,
        {
          id: nextLocalId(),
          role: 'user',
          content: body,
          ...(pageHint ? { pageHint } : {}),
          ...(refs.length ? { refs } : {}),
        },
        { id: assistantId, role: 'assistant', content: '', streaming: true },
      ],
      approvals: [],
      streaming: true,
      queuePosition: null,
      queuedSteers: [],
      turnStats: { ...EMPTY_STATS, samples: [] },
    }))
    onQueued?.(true)

    // 本轮的 SSE → 状态更新集中在 turn-handlers（正文/思考/工具行/审批/排队/统计）
    const { handlers, finishAssistant } = createTurnHandlers(assistantId, set)

    controller = new AbortController()
    try {
      const resp = await copilotApi.openMessageStream(sessionId, composed, controller.signal)
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)
      await consumeAgentStream(resp, handlers)
      finishAssistant()
      set((s) => ({ turnStats: { ...s.turnStats, doneAt: s.turnStats.doneAt ?? Date.now() } }))
    } catch {
      finishAssistant()
      const aborted = controller?.signal.aborted
      if (get().sessionId) {
        // 服务端会把已流出的部分回答落库（truncated）：无论主动停止还是
        // 网络中断，都重拉历史对齐，再决定要不要提示错误
        await get().switchSession(get().sessionId)
      }
      if (!aborted) {
        set({ lastError: '连接中断，请重试' })
      }
    } finally {
      controller = null
      set({ streaming: false, queuePosition: null })
    }
  },

  stop: () => {
    controller?.abort()
  },

  decide: async (approvalId, approved, reason = '') => {
    set((s) => ({
      approvals: s.approvals.map((a) =>
        a.approvalId === approvalId ? { ...a, decided: approved ? 'approved' : 'rejected' } : a,
      ),
    }))
    try {
      await copilotApi.decideApproval(approvalId, approved, reason)
    } catch {
      // 本地已标记；提交失败不再回滚——服务端 300s 超时按拒绝处理（fail-closed）
    }
  },

  steer: async (text) => {
    const trimmed = text.trim()
    const sessionId = get().sessionId
    if (!trimmed || !sessionId || !get().streaming || get().steering) return
    set({ steering: true })
    try {
      await copilotApi.steerSession(sessionId, trimmed)
      set((s) => ({ queuedSteers: [...s.queuedSteers, trimmed] }))
    } catch (err) {
      // 409：本轮刚结束（settle），插话没有对象；其余按网络失败提示
      const status = err instanceof HTTPError ? err.response.status : 0
      set({ lastError: status === 409 ? '本轮对话已结束，插话未送达' : '插话发送失败，请重试' })
    } finally {
      set({ steering: false })
    }
  },

  revokeQueuedSteers: async () => {
    const sessionId = get().sessionId
    if (!sessionId || get().queuedSteers.length === 0) return
    try {
      await copilotApi.clearSessionQueue(sessionId)
      set({ queuedSteers: [] })
    } catch {
      set({ lastError: '撤回插话失败，请重试' })
    }
  },

  submitTask: async (text) => {
    const trimmed = text.trim()
    if (!trimmed || get().streaming) return
    set({ lastError: null })
    try {
      const receipt = await copilotApi.submitAgentTask(trimmed, '', get().context ?? undefined)
      // 受理即切到任务会话：侧栏徽标 + 轮询由此展开；跑完的通知消息
      // 写进会话历史，refreshHistory（面板轮询触发）后即可见
      await get().switchSession(receipt.session_id)
    } catch {
      set({ lastError: '提交后台任务失败，请稍后重试' })
    }
  },

  loadPendingApprovals: async () => {
    try {
      const items = await copilotApi.fetchPendingApprovals()
      set((s) => {
        // 只补前端不知道的：已渲染（含已决定）的不动，避免覆盖本地终态；
        // 已超窗的僵尸项不合并（服务端懒清理之外的双保险），并顺带清除旧卡
        const known = new Set(s.approvals.map((a) => a.approvalId))
        const fresh = items
          .filter((i) => !known.has(i.approval_id) && !isExpiredOfflineItem(i))
          .map(pendingItemToApproval)
        const pruned = s.approvals.filter(
          (a) => !(a.offline && !a.decided && Date.now() - a.receivedAt > APPROVAL_OFFLINE_WINDOW_S * 1000),
        )
        if (fresh.length === 0 && pruned.length === s.approvals.length) return s
        return { approvals: [...pruned, ...fresh] }
      })
    } catch {
      // 待审列表拉不到不阻塞主流程（下一流结束/面板重开会再试）
    }
  },

  dismissApproval: (approvalId) => {
    set((s) => ({ approvals: s.approvals.filter((a) => a.approvalId !== approvalId) }))
  },

  rateMessage: async (messageId, rating) => {
    const prev = get().messages.find((m) => m.id === `db-${messageId}`)?.rating
    const apply = (r?: 'up' | 'down') =>
      set((s) => ({
        messages: s.messages.map((m) => (m.id === `db-${messageId}` ? { ...m, rating: r } : m)),
      }))
    apply(rating === 'none' ? undefined : rating)
    try {
      await copilotApi.rateMessage(messageId, rating)
    } catch {
      apply(prev) // 失败回滚
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

  reset: () => {
    get().stop()
    set({
      sessionId: null,
      messages: [],
      approvals: [],
      streaming: false,
      loadingHistory: false,
      lastError: null,
      turnStats: { ...EMPTY_STATS },
      queuePosition: null,
      queuedSteers: [],
      steering: false,
      context: null,
      pendingFiles: [],
      pendingRefs: [],
      uploadingAttachments: false,
      draggingFiles: false,
    })
    resetUploadReceipts()
    storeSession(null)
  },
}))
