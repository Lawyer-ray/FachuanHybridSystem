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
import { DEFAULT_AGENT_KIND } from '../domain'
import { uploadAttachmentsAndCompose } from '../outgoing'
import { storeSession } from '../persistence'
import { consumeAgentStream } from '../streaming'
import { createTurnHandlers } from '../turn-handlers'
import type { AgentBackendOption, CopilotState, TurnStats } from '../types'
import { resolveCapabilities } from './backends'
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
 * 本轮双答要跑哪几个后端（顺序 = 栏的左右顺序）。
 *
 * 主栏 = 会话自己选的（新会话取 `selectedAgentKind`，空串时后端默认 pi），次栏 =
 * 清单里第一个「可用的、且不是主」的后端。规则与后端 `dual.pick_secondary`
 * 同口径，但前端必须在**开流前**就知道有两栏——否则事件到了才发现没有对应气泡，
 * 次答的正文会全部落进主栏（表现是两栏内容一模一样）。
 *
 * 与后端口径的唯一差别：后端按注册表顺序取，前端按 `/agent/backends` 清单顺序取。
 * 两个来源同一个注册表，顺序一致；清单没拉到（`backends` 为空）时返回单栏，
 * 行为退回到「不加双答」，不会造出两个空栏。
 */
export function dualAgentKinds(state: Partial<Pick<CopilotState, 'backends' | 'selectedAgentKind'>>): string[] {
  const primary = state.selectedAgentKind || DEFAULT_AGENT_KIND
  const backends = state.backends ?? []
  const secondary = backends.find(
    (b) => b.available && b.kind !== primary && resolveCapabilities(backends, b.kind).streaming,
  )
  return secondary ? [primary, secondary.kind] : []
}

/**
 * 本部署能不能开同题双答：清单里存在「可用的、且不是当前主后端」的第二个后端。
 *
 * 与 {@link dualAgentKinds} 同源（后者多要求 `streaming` 能力）：这里只判「有没有
 * 第二家」，用来决定开关能不能点；真正的栏数由 dualAgentKinds 决定。
 */
export function dualAvailableFor(backends: AgentBackendOption[] | undefined, selectedAgentKind: string): boolean {
  const primary = selectedAgentKind || DEFAULT_AGENT_KIND
  // 清单可能是 undefined：组件测试常只 mock 部分 state。这里按「没有第二家」
  // 处理（开关置灰），而不是抛错——渲染期抛错会把整个面板打成白屏。
  return (backends ?? []).some((b) => b.available && b.kind !== primary)
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
      // 新会话带上用户选的 agent 后端（空串 = 不指定，后端用默认值 pi）。
      // 只在建会话这一刻生效：已有会话换后端会丢掉上下文，见 store/backends.ts。
      try {
        sessionId = (await copilotApi.createSession('', get().context ?? undefined, pre.selectedAgentKind)).session_id
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

    // 双答开关：本轮要几栏。双答时两栏并排（各带 agent 标签），单后端时只有一条
    // ——单条路径必须与引入本功能前**完全一致**（那条的 agentKind 留空，渲染不加
    // 标签，见 domain/dual.isDualTurn）。
    const dualAgents = pre.dual ? dualAgentKinds(pre) : []
    const assistantId = nextLocalId()
    // 每个 agent 一栏：id 先算好，气泡与事件路由共用同一份——两处各 nextLocalId()
    // 会造出「气泡挂在 A 的 id、事件写进 B 的 id」这种只差一个字难以发现的错配。
    const assistantByAgent: Record<string, string> =
      dualAgents.length > 1
        ? Object.fromEntries(dualAgents.map((kind, i) => [kind, i === 0 ? assistantId : nextLocalId()]))
        : {}
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
        // 单后端：一条不带 agentKind 的气泡（与历史渲染口径一致：空串 = 旧行为）
        ...(dualAgents.length > 1
          ? dualAgents.map((kind) => ({
              id: assistantByAgent[kind]!,
              role: 'assistant' as const,
              content: '',
              streaming: true,
              agentKind: kind,
            }))
          : [{ id: assistantId, role: 'assistant' as const, content: '', streaming: true }]),
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

    // 本轮的 SSE → 状态更新集中在 turn-handlers（正文/思考/工具行/审批/排队/统计）。
    // 双答时按事件里的 agent 分到各自气泡：路由表的键是 kind，缺 agent 的事件
    // 落到第一条（主栏）——鉴于是「旧口径」且双答前只有一条气泡。
    const { handlers, finishAssistant } = createTurnHandlers(
      assistantId,
      set,
      (kind) => assistantByAgent[kind] ?? assistantId,
      dualAgents.length > 1 ? 2 : 1,
    )

    controller = new AbortController()
    try {
      const resp = await copilotApi.openMessageStream(sessionId, composed, controller.signal, pre.dual)
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
