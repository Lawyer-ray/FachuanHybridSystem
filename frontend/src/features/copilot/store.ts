/**
 * Copilot 全局状态：转录、审批卡与流式收发。
 *
 * 流的生命周期归 store（模块级 Zustand）而非组件——收起面板不中断流，
 * 重新展开继续看；「停止生成」= AbortController 断开，服务端会把已流出
 * 的部分回答落库（truncated），随后重拉历史对齐。
 * 会话列表这类服务端状态走 react-query（SessionSidebar），不进本 store。
 *
 * 本 store 还承载三类「后端已有、前端补齐」的编排：
 * - 运行中插话（steer / 撤回）：queuedSteers 记录本轮已插话文本
 * - 后台任务（submitTask）：提交后切到任务会话，跑完由面板轮询刷新
 * - 离线审批（loadPendingApprovals）：后台任务挂起的高危工具调用，
 *   面板打开/每轮流结束后拉一次待审列表并渲染成审批卡
 */

import { flushSync } from 'react-dom'
import { HTTPError } from 'ky'
import { create } from 'zustand'

import * as copilotApi from './api'
import { historyToMessages, nextLocalId } from './domain'
import { consumeAgentStream } from './streaming'
import { createTurnHandlers } from './turn-handlers'
import type { ChatMessage, PendingApproval, PendingApprovalItem, TurnStats } from './types'

const EMPTY_STATS: TurnStats = {
  firstDeltaAt: null,
  lastDeltaAt: null,
  doneAt: null,
  estTokens: 0,
  exactTokens: null,
  samples: [],
}

const SESSION_KEY = 'copilot:session'

/**
 * 会话内容切换的局部 crossfade（View Transition API）：
 * 回调里的状态变更会被浏览器捕捉为旧/新两帧，仅对带 view-transition-name
 * 的消息区播放淡出淡入（见 copilot.css）。不支持的浏览器（或用户开了
 * 「减弱动态效果」）直接执行回调，无动画降级。
 */
function withViewTransition(update: () => void): void {
  // node 测试环境 / SSR 无 document；不支持的浏览器降级为直接更新
  if (typeof document === 'undefined') {
    update()
    return
  }
  const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown }
  if (typeof doc.startViewTransition !== 'function' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    update()
    return
  }
  // 并发过渡（上一段 200ms 未播完、下一段又起）时浏览器会 skip 旧过渡，
  // 其 ready/finished promise 会被 reject——不接住会变成未处理的 rejection
  const transition = doc.startViewTransition(() => {
    flushSync(update)
  }) as { ready?: Promise<void>; finished?: Promise<void> }
  transition.ready?.catch(() => {})
  transition.finished?.catch(() => {})
}

function readStoredSession(): string | null {
  try {
    return localStorage.getItem(SESSION_KEY) || null
  } catch {
    return null
  }
}

function storeSession(id: string | null): void {
  try {
    if (id) localStorage.setItem(SESSION_KEY, id)
    else localStorage.removeItem(SESSION_KEY)
  } catch {
    /* 无 localStorage 环境（单测）忽略 */
  }
}

/** 离线待审批 → 审批卡模型（倒计时按服务端 created_at 起算） */
function pendingItemToApproval(item: PendingApprovalItem): PendingApproval {
  return {
    approvalId: item.approval_id,
    toolName: item.tool_name,
    toolArgs: item.tool_args ?? {},
    message: '',
    receivedAt: new Date(item.created_at).getTime() || Date.now(),
    riskLevel: item.risk_level,
    offline: true,
  }
}

interface CopilotState {
  sessionId: string | null
  messages: ChatMessage[]
  approvals: PendingApproval[]
  streaming: boolean
  loadingHistory: boolean
  lastError: string | null
  /** 本轮输出统计：流式期间驱动实时 tok/s，结束后展示精确 token 与平均速度 */
  turnStats: TurnStats
  /** 池满排队中：队列名次（1 起）；null = 不在排队 */
  queuePosition: number | null
  /** 本轮已插话（steer）且尚未撤回的文本 */
  queuedSteers: string[]
  /** 插话请求在途（防重复提交） */
  steering: boolean
  /** 切换会话（null = 新对话）；会先停掉在途流再回放历史 */
  switchSession: (id: string | null) => Promise<void>
  /** 发消息并消费 SSE 流；无会话时先创建 */
  send: (text: string) => Promise<void>
  /** 停止生成（中断在途流） */
  stop: () => void
  /** 审批决定：本地即时标记，提交失败保持现状（服务端超时 fail-closed） */
  decide: (approvalId: string, approved: boolean) => Promise<void>
  /** 运行中插话：当前轮工具调用后、下次模型调用前生效 */
  steer: (text: string) => Promise<void>
  /** 撤回已排队未生效的全部插话 */
  revokeQueuedSteers: () => Promise<void>
  /** 提交后台任务（origin=task）：受理后切到该任务会话 */
  submitTask: (text: string) => Promise<void>
  /** 拉取离线待审批并合并进审批卡（面板打开 / 每轮流结束时调用） */
  loadPendingApprovals: () => Promise<void>
  /** 重拉当前会话历史（后台任务跑完后刷新转录用；流式中跳过） */
  refreshHistory: () => Promise<void>
  /** 登出清理（换账号不得残留上一账号的会话内容） */
  reset: () => void
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
          set({ messages: historyToMessages(rows), loadingHistory: false })
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

  send: async (text) => {
    const trimmed = text.trim()
    if (!trimmed || get().streaming) return
    set({ lastError: null })

    // 本轮发送归属哪个会话：await 期间用户可能切会话/开新对话，
    // 迟到结果必须丢弃，否则会覆盖用户刚选中的会话并把消息推进去
    const startedSessionId = get().sessionId
    let sessionId = startedSessionId
    if (!sessionId) {
      try {
        sessionId = (await copilotApi.createSession()).session_id
      } catch {
        set({ lastError: '创建会话失败，请稍后重试' })
        return
      }
      // createSession 在途期间用户已切走：不占用新会话，也不污染当前视图
      if (get().sessionId !== startedSessionId) return
      set({ sessionId })
      storeSession(sessionId)
    }

    const assistantId = nextLocalId()
    set((s) => ({
      messages: [
        ...s.messages,
        { id: nextLocalId(), role: 'user', content: trimmed },
        { id: assistantId, role: 'assistant', content: '', streaming: true },
      ],
      approvals: [],
      streaming: true,
      queuePosition: null,
      queuedSteers: [],
      turnStats: { ...EMPTY_STATS, samples: [] },
    }))

    // 本轮的 SSE → 状态更新集中在 turn-handlers（正文/思考/工具行/审批/排队/统计）
    const { handlers, finishAssistant } = createTurnHandlers(assistantId, set)

    controller = new AbortController()
    try {
      const resp = await copilotApi.openMessageStream(sessionId, trimmed, controller.signal)
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

  decide: async (approvalId, approved) => {
    set((s) => ({
      approvals: s.approvals.map((a) =>
        a.approvalId === approvalId ? { ...a, decided: approved ? 'approved' : 'rejected' } : a,
      ),
    }))
    try {
      await copilotApi.decideApproval(approvalId, approved)
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
      const receipt = await copilotApi.submitAgentTask(trimmed)
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
        // 只补前端不知道的：已渲染（含已决定）的不动，避免覆盖本地终态
        const known = new Set(s.approvals.map((a) => a.approvalId))
        const fresh = items.filter((i) => !known.has(i.approval_id)).map(pendingItemToApproval)
        return fresh.length > 0 ? { approvals: [...s.approvals, ...fresh] } : s
      })
    } catch {
      // 待审列表拉不到不阻塞主流程（下一流结束/面板重开会再试）
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
    })
    storeSession(null)
  },
}))
