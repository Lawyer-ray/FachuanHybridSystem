/**
 * store slice：一轮对话（发送、流生命周期、插话、后台任务）。
 *
 * 细节在同域模块：SSE 帧消费 streaming.ts、轮处理器 turn-handlers.ts、
 * 附件出站 outgoing.ts——本文件只管编排与竞态守卫。
 */

import { HTTPError } from 'ky'

import * as copilotApi from '../api'
import {
  buildBizHintBlock,
  buildSelectionQuoteBlock,
  nextLocalId,
  splitBizHintLine,
  splitPageHintLine,
  splitQuoteBlock,
  splitRefBlocks,
} from '../domain'
import { uploadAttachmentsAndCompose } from '../outgoing'
import { storeSession } from '../persistence'
import { consumeAgentStream } from '../streaming'
import { createTurnHandlers } from '../turn-handlers'
import type { CopilotState, TurnStats } from '../types'
import { bumpSessionEpoch } from './session-epoch'
import type { Slice } from './slice'

/** 轮次统计初值（send 入列时复位；reset 也复用它） */
export const EMPTY_STATS: TurnStats = {
  firstDeltaAt: null,
  lastDeltaAt: null,
  doneAt: null,
  estTokens: 0,
  exactTokens: null,
  samples: [],
}

/**
 * 在途流的中止句柄（模块级单例，随 store 生命周期）。
 *
 * 归属本 slice：只有 send 创建/清除它、只有 stop 消费它。decide() 等动作
 * **不碰**它——曾因某路径在流未结束时把它置空，导致 stop() 成 no-op、
 * streaming 永远为 true（2026-10 审查 F1）。
 */
let controller: AbortController | null = null

export type TurnSlice = Pick<
  CopilotState,
  'send' | 'stop' | 'steer' | 'revokeQueuedSteers' | 'submitTask'
>

export const createTurnSlice: Slice<TurnSlice> = (set, get) => ({
  send: async (text, onQueued) => {
    const trimmed = text.trim()
    if (!trimmed || get().streaming || get().uploadingAttachments || get().sending) {
      onQueued?.(false)
      return
    }
    // 锁贯穿全程：建会话/上传附件的每个 await 期间，Composer 的发送、回形针、
    // 后台模式三个按钮都靠它置忙——漏清一处就是永久锁，所以只在真正入列
    // 与每个早退分支上清
    set({ lastError: null, sending: true })

    // 锚点注入（模型据此知道自己服务谁、用户在哪个页面）：
    // - 业务范围内（详情页工作区/浮层 context）：每轮注入归属锚点——pi 的
    //   compaction 可能把首轮上下文压掉，不重复注入模型就会「失忆」反问
    //   「哪个案件」（实测发生过）；含实体 id，模型可直接调工具读绑定文件夹。
    // - 通用模式：页面变化后首条才注页面锚点（历史不刷屏）。
    const pre = get()
    let outgoingText = trimmed
    if (pre.context) {
      outgoingText = buildBizHintBlock(pre.context, trimmed)
    } else if (pre.pageHint && pre.pageHint !== pre.lastPageHintSent) {
      outgoingText = `[当前页面：${pre.pageHint}]\n${trimmed}`
      set({ lastPageHintSent: pre.pageHint })
    }
    // 框选引用（豆包式）：引用块单独成行缀在锚点后，模型据此可结合原文件
    // （含 contract_id + subpath）回答；回放时由 splitQuoteBlock 还原成卡
    if (pre.pendingQuote) {
      outgoingText = `${buildSelectionQuoteBlock(pre.pendingQuote)}\n${outgoingText}`
    }

    // 本轮发送归属哪个会话：await 期间用户可能切会话/开新对话，
    // 迟到结果必须丢弃，否则会覆盖用户刚选中的会话并把消息推进去
    const startedSessionId = get().sessionId
    let sessionId = startedSessionId
    if (!sessionId) {
      try {
        sessionId = (await copilotApi.createSession('', get().context ?? undefined)).session_id
      } catch {
        set({ lastError: '创建会话失败，请稍后重试', sending: false })
        onQueued?.(false)
        return
      }
      // createSession 在途期间用户已切走：不占用新会话，也不污染当前视图
      if (get().sessionId !== startedSessionId) {
        set({ sending: false })
        onQueued?.(false)
        return
      }
      bumpSessionEpoch()
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
      set({ lastError: '附件/引用准备失败，请重试（已保留，重试不会重复上传）', sending: false })
      onQueued?.(false)
      return
    }
    // 附件上传在途期间用户可能切走：迟到结果丢弃（chips 保留，回执已缓存，
    // 下次发送不重复上传），不把消息推进新选中的会话
    if (get().sessionId !== sessionId) {
      set({ sending: false })
      onQueued?.(false)
      return
    }
    if (pendingFiles.length > 0 || pendingRefs.length > 0) set({ pendingFiles: [], pendingRefs: [] })
    if (pre.pendingQuote) set({ pendingQuote: null })
    const composed = outgoing.composed

    const assistantId = nextLocalId()
    // 与历史回放同一解析：本地即时渲染也把页面/业务锚点、引用块还原成 chip，两侧不漂移
    const { pageHint, body: noHint } = splitPageHintLine(composed)
    const { bizHint, body: noBiz } = splitBizHintLine(noHint)
    const { refs, body: noRefs } = splitRefBlocks(noBiz)
    const { quote, body } = splitQuoteBlock(noRefs)
    set((s) => ({
      messages: [
        ...s.messages,
        {
          id: nextLocalId(),
          role: 'user',
          content: body,
          ...(pageHint ? { pageHint } : {}),
          ...(bizHint ? { bizHint } : {}),
          ...(refs.length ? { refs } : {}),
          ...(quote ? { quote } : {}),
        },
        { id: assistantId, role: 'assistant', content: '', streaming: true },
      ],
      approvals: [],
      streaming: true,
      // 消息已入列、流已开：置忙交给 streaming，sending 在此解除
      sending: false,
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
})
