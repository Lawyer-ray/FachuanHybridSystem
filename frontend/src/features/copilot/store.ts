/**
 * Copilot 全局状态：转录、审批卡与流式收发。
 *
 * 流的生命周期归 store（模块级 Zustand）而非组件——收起面板不中断流，
 * 重新展开继续看；「停止生成」= AbortController 断开，服务端会把已流出
 * 的部分回答落库（truncated），随后重拉历史对齐。
 * 会话列表这类服务端状态走 react-query（SessionSidebar），不进本 store。
 */

import { create } from 'zustand'

import * as copilotApi from './api'
import { historyToMessages, nextLocalId, parseSseEvent, takeSseFrames } from './domain'
import type { ChatMessage, PendingApproval } from './types'

const SESSION_KEY = 'copilot:session'

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

  switchSession: async (id) => {
    get().stop()
    set({ sessionId: id, messages: [], approvals: [], lastError: null })
    storeSession(id)
    if (!id) return
    set({ loadingHistory: true })
    try {
      const rows = await copilotApi.fetchHistory(id)
      // 等待期间用户可能又切走了：只回填仍是当前会话的结果
      if (get().sessionId === id) set({ messages: historyToMessages(rows) })
    } catch {
      if (get().sessionId === id) set({ lastError: '加载会话历史失败' })
    } finally {
      if (get().sessionId === id) set({ loadingHistory: false })
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
    }))

    const appendAssistant = (chunk: string) => {
      if (!chunk) return
      set((s) => ({
        messages: s.messages.map((m) => (m.id === assistantId ? { ...m, content: m.content + chunk } : m)),
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
            case 'delta':
              appendAssistant(event.content)
              break
            case 'tool_call':
              set((s) => ({
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
              }))
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
              break
            default:
              break // meta / activity 不入转录
          }
        }
      }
      finishAssistant()
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
    set({ sessionId: null, messages: [], approvals: [], streaming: false, loadingHistory: false, lastError: null })
    storeSession(null)
  },
}))
