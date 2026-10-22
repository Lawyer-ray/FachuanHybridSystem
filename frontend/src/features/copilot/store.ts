/**
 * Copilot 全局状态：转录、审批卡与流式收发。
 *
 * 流的生命周期归 store（模块级 Zustand）而非组件——收起面板不中断流，
 * 重新展开继续看；「停止生成」= AbortController 断开，服务端会把已流出
 * 的部分回答落库（truncated），随后重拉历史对齐。
 * 会话列表这类服务端状态走 react-query（SessionSidebar），不进本 store。
 */

import { flushSync } from 'react-dom'
import { create } from 'zustand'

import * as copilotApi from './api'
import {
  estimateTokens,
  historyToMessages,
  nextLocalId,
  parseSseEvent,
  takeSseFrames,
} from './domain'
import type { ChatMessage, PendingApproval, TurnStats } from './types'

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

interface CopilotState {
  sessionId: string | null
  messages: ChatMessage[]
  approvals: PendingApproval[]
  streaming: boolean
  loadingHistory: boolean
  lastError: string | null
  /** 本轮输出统计：流式期间驱动实时 tok/s，结束后展示精确 token 与平均速度 */
  turnStats: TurnStats
  /** 切换会话（null = 新对话）；会先停掉在途流再回放历史 */
  switchSession: (id: string | null) => Promise<void>
  /** 发消息并消费 SSE 流；无会话时先创建 */
  send: (text: string) => Promise<void>
  /** 停止生成（中断在途流） */
  stop: () => void
  /** 审批决定：本地即时标记，提交失败保持现状（服务端超时 fail-closed） */
  decide: (approvalId: string, approved: boolean) => Promise<void>
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

  switchSession: async (id) => {
    const prev = get()
    // 同会话且视图已就绪：不重复拉取、不播切换动画（stop 后的重拉 streaming 仍为 true，放行）
    if (id === prev.sessionId && !prev.streaming && (id !== null || prev.messages.length === 0)) return
    get().stop()
    withViewTransition(() => {
      set({ sessionId: id, messages: [], approvals: [], lastError: null, loadingHistory: id !== null })
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

    let sessionId = get().sessionId
    if (!sessionId) {
      try {
        sessionId = (await copilotApi.createSession()).session_id
        set({ sessionId })
        storeSession(sessionId)
      } catch {
        set({ lastError: '创建会话失败，请稍后重试' })
        return
      }
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
      turnStats: { ...EMPTY_STATS, samples: [] },
    }))

    const appendAssistant = (chunk: string) => {
      if (!chunk) return
      set((s) => ({
        messages: s.messages.map((m) =>
          // 首个正文 delta 到达 → 思考阶段结束（供前端收起/打勾）
          m.id === assistantId ? { ...m, content: m.content + chunk, thinkingDone: true } : m,
        ),
      }))
    }
    const appendThinking = (chunk: string) => {
      if (!chunk) return
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === assistantId ? { ...m, thinking: (m.thinking ?? '') + chunk } : m,
        ),
      }))
    }
    const finishAssistant = () => {
      set((s) => ({
        messages: s.messages.map((m) => (m.id === assistantId ? { ...m, streaming: false } : m)),
      }))
    }

    controller = new AbortController()
    try {
      const resp = await copilotApi.openMessageStream(sessionId, trimmed, controller.signal)
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const { frames, rest } = takeSseFrames(buffer)
        buffer = rest
        for (const frame of frames) {
          const event = parseSseEvent(frame)
          if (!event) continue
          switch (event.type) {
            case 'thinking':
              // 思考增量：单独累积到 thinking 字段，不计入正文也不计入 token 速率估算
              appendThinking(event.content)
              break
            case 'delta':
              appendAssistant(event.content)
              set((s) => {
                const now = Date.now()
                const estTokens = s.turnStats.estTokens + estimateTokens(event.content)
                const samples = [...s.turnStats.samples, [now, estTokens] as [number, number]]
                // 只留最近 4 秒的采样，窗口计算足够（2s 窗口）
                const cutoff = now - 4000
                const start = samples.findIndex(([t]) => t >= cutoff)
                return {
                  turnStats: {
                    ...s.turnStats,
                    firstDeltaAt: s.turnStats.firstDeltaAt ?? now,
                    lastDeltaAt: now,
                    estTokens,
                    samples: start > 0 ? samples.slice(start) : samples,
                  },
                }
              })
              break
            case 'tool_call':
              // pi 对同一工具调用可能发多条 message_end（arguments 渐进完整），
              // 以 tool_call_id 去重：已有则原行保留，没有才追加
              set((s) => {
                if (event.tool_call_id && s.messages.some((m) => m.toolCallId === event.tool_call_id)) {
                  return s
                }
                return {
                  messages: [
                    ...s.messages,
                    {
                      id: nextLocalId(),
                      role: 'tool',
                      content: '',
                      toolName: event.name,
                      toolCallId: event.tool_call_id,
                    },
                  ],
                }
              })
              break
            case 'tool_result': {
              const matchId = event.tool_call_id
              set((s) => ({
                // tool_call 与 tool_result 以 tool_call_id 归并；缺 id 时落最近一个空 tool 气泡
                messages: s.messages.map((m, i) => {
                  const byId = m.role === 'tool' && matchId && m.toolCallId === matchId
                  const lastEmpty = !matchId && m.role === 'tool' && !m.content && s.messages.slice(i + 1).every((x) => x.role !== 'tool')
                  return byId || lastEmpty ? { ...m, content: String(event.result ?? '') } : m
                }),
              }))
              break
            }
            case 'usage':
              set((s) => ({
                turnStats: {
                  ...s.turnStats,
                  exactTokens: (s.turnStats.exactTokens ?? 0) + event.output_tokens,
                },
              }))
              break
            case 'approval_request':
              set((s) => ({
                approvals: [
                  ...s.approvals,
                  {
                    approvalId: event.approval_id,
                    toolName: event.tool_name,
                    toolArgs: event.tool_args ?? {},
                    message: event.message,
                    receivedAt: Date.now(),
                  },
                ],
              }))
              break
            case 'error':
              set({ lastError: event.message })
              finishAssistant()
              break
            case 'done':
              finishAssistant()
              set((s) => ({ turnStats: { ...s.turnStats, doneAt: Date.now() } }))
              break
            default:
              break // meta / activity 不入转录
          }
        }
      }
      finishAssistant()
      set((s) => ({ turnStats: { ...s.turnStats, doneAt: s.turnStats.doneAt ?? Date.now() } }))
    } catch {
      finishAssistant()
      if (controller?.signal.aborted) {
        // 用户主动停止：服务端已把部分回答落库（truncated），重拉历史对齐
        await get().switchSession(get().sessionId)
      } else {
        set({ lastError: '连接中断，请重试' })
      }
    } finally {
      controller = null
      set({ streaming: false })
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
    })
    storeSession(null)
  },
}))
