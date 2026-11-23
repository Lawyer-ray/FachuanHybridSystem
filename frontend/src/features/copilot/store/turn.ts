/**
 * store slice：一轮对话（发送、流生命周期、插话、后台任务）。
 *
 * 细节在同域模块：SSE 帧消费 streaming.ts、轮处理器 turn-handlers.ts、
 * 附件出站 outgoing.ts、发送流水线的各阶段 turn-send.ts——本文件只管编排与
 * 竞态守卫。
 */

import { HTTPError } from 'ky'

import * as copilotApi from '../api'
import { emptyTurnStats, nextLocalId, ratableMessageId } from '../domain'
import { MAX_ANSWERS } from '../domain'
import { consumeAgentStream } from '../streaming'
import { createTurnHandlers } from '../turn-handlers'
import type { AgentSpec, CopilotState, TurnStats } from '../types'
import { resolveCapabilities } from './backends'
import type { Slice } from './slice'
import {
  beginAnswerTurn,
  buildOutgoingText,
  ensureOutgoing,
  ensureSession,
  runAnswerStream,
} from './turn-send'

/** 轮次统计初值（形状定义在 domain/usage，store 与 turn-handlers 共用同一份） */
export const EMPTY_STATS: TurnStats = emptyTurnStats()

/**
 * 本轮实际要跑哪几个 agent（顺序 = 栏的左右顺序）。
 *
 * 输入是用户在工具栏里选的那几个（`answerAgents`），这里只做两件事：
 * 1. **按清单过滤**：不可用（缺 SDK / 没配 LLM）或声明不支持流式的后端去掉——
 *    留着只会多一个永远空着的栏；
 * 2. **截到上限**：{@link MAX_ANSWERS}（与后端同口径，超出后端直接 400）。
 *
 * 返回 `[]` = 不指定，后端单跑会话默认后端（单栏）。返回单元素 = 单跑该后端。
 *
 * 为什么前端必须在**开流前**知道有几栏：事件到了才发现没有对应气泡的话，
 * 那一栏的正文会全部落进第一栏（表现是两栏内容一模一样）。
 */
export function resolveAnswerAgents(
  state: Partial<Pick<CopilotState, 'backends' | 'answerAgents'>>,
): string[] {
  const backends = state.backends ?? []
  const picked = state.answerAgents ?? []
  const usable = picked.filter((kind) => {
    const option = backends.find((b) => b.kind === kind)
    // 清单没拉到（`backends` 为空）时信任用户的选择：不是每次都能拉成功，
    // 而按「找不到就不跑」会让多答在冷启动时安静地退化成单栏。
    if (!option) return true
    return option.available && resolveCapabilities(backends, kind).streaming
  })
  return usable.slice(0, MAX_ANSWERS)
}

/**
 * 本轮下发的参与方清单：`[{kind, model?}]`（顺序 = 栏的左右顺序）。
 *
 * 与 {@link resolveAnswerAgents} 的栏清单**同源**：先按可用性过滤、截到上限，
 * 再逐栏挂上律师指定的模型。两件事分开算，是为了让「这一轮几栏」与「每栏哪个
 * 模型」不会各自跑出不同的栏序。
 *
 * **`model` 只在有值时才出现在元素上**：缺省字段 = 用平台默认模型，与引入本字段
 * 前发纯字符串 `"pi"` 完全等价（后端 `AgentSpecIn.model` 缺省为 None）。存空串
 * 或不发会让同一件事有两种写法——后端口径是 `None`，前端就只表达 None。
 *
 * 显式指定了清单外的模型名也照发：清单可能过期（后端刚上新模型）、也可能拉取
 * 失败，而那时已有选择不该被前端悄悄改掉——真不认的话后端会报错，比静默改模型好。
 */
export function resolveAnswerSpecs(
  state: Partial<Pick<CopilotState, 'backends' | 'answerAgents' | 'answerModels'>>,
): AgentSpec[] {
  const models = state.answerModels ?? {}
  return resolveAnswerAgents(state).map((kind) => {
    const model = models[kind]
    return model ? { kind, model } : { kind }
  })
}

/**
 * 能不能再多选一个 agent（工具栏据此置灰未选项）。
 *
 * 只判**数量**：具体某个后端可用与否由清单项自己的 `available` 决定，
 * 两件事分开判，UI 才能说清「已选满」还是「这个后端不可用」。
 */
export function canAddAnswerAgent(picked: readonly string[]): boolean {
  return picked.length < MAX_ANSWERS
}

/**
 * 在途流的中止句柄（模块级单例，随 store 生命周期）。
 *
 * 归属本 slice：send / regenerate 创建它、stop 消费它；send 的清除由 turn-send 的
 * runAnswerStream 在收尾时通过 releaseController 回调完成。decide() 等动作
 * **不碰**它——曾因某路径在流未结束时把它置空，导致 stop() 成 no-op、
 * streaming 永远为 true（2026-10 审查 F1）。
 */
let controller: AbortController | null = null

export type TurnSlice = Pick<
  CopilotState,
  'send' | 'regenerate' | 'stop' | 'steer' | 'revokeQueuedSteers' | 'submitTask'
>

export const createTurnSlice: Slice<TurnSlice> = (set, get) => ({
  send: async (text, onQueued) => {
    const trimmed = text.trim()
    if (!trimmed || get().streaming || get().uploadingAttachments || get().sending) {
      onQueued?.(false)
      return
    }
    // 锁贯穿全程：建会话/上传附件的每个 await 期间，Composer 的发送、回形针、
    // 后台模式三个按钮都靠它置忙——漏清一处就是永久锁。本函数只在入列前持锁，
    // 各早退分支的清锁与 `onQueued(false)` 都在 turn-send 对应阶段里。
    set({ lastError: null, sending: true })

    const pre = get()
    const outgoingText = buildOutgoingText(pre, trimmed, set)
    // 本轮要几栏：选中的 agent 清单（过滤不可用 / 截到上限后才是真实栏数）。
    // 单栏路径必须与多答前**完全一致**（agentKind 留空、渲染不加标签）。
    const turnAgents = resolveAnswerAgents(pre)
    // 新会话归属 = 本轮勾选的第一个（顺序 = 栏的左右顺序）；未勾 / 全不可用退回
    // selectedAgentKind（部署默认）。❗必须用**过滤后**的清单（见 resolveAnswerAgents）：
    // 直接取 answerAgents[0] 会让「勾了一个缺 SDK 的后端」变成会话归属，而它不在本轮。
    const ownerKind = turnAgents[0] || pre.selectedAgentKind
    const sessionId = await ensureSession(ownerKind, pre.context, get, set, onQueued)
    if (!sessionId) return
    const composed = await ensureOutgoing(sessionId, outgoingText, pre.pendingQuote, get, set, onQueued)
    if (composed === null) return
    // 每栏带模型（缺省不带 = 平台默认）；顺序与 turnAgents 逐一对应
    const turnSpecs = resolveAnswerSpecs(pre)
    const turn = beginAnswerTurn({
      composed,
      turnAgents,
      turnSpecs,
      initialStats: EMPTY_STATS,
      set,
      onQueued,
    })
    controller = new AbortController()
    await runAnswerStream({
      ctrl: controller,
      sessionId,
      composed,
      turnAgents,
      turnSpecs,
      turn,
      // 流收尾时释放模块级句柄（顺序：先释放、再解除 streaming，见 runAnswerStream）
      releaseController: () => {
        controller = null
      },
      get,
      set,
    })
  },
  regenerate: async (fromMessageId, mode) => {
    const sessionId = get().sessionId
    if (!sessionId || get().streaming) return
    const target = get().messages.find((message) => ratableMessageId(message) === fromMessageId)
    if (!target) {
      set({ lastError: '这条回答还没落库，暂时不能重生成' })
      return
    }
    const lane = target.agentKind ?? ''
    // 新气泡承接这次重放的输出；旧气泡原样留着——服务端已把它标成 superseded，
    // 流结束后拉一次历史就看不见了（连点重生成时同栏会同时出现两条，是预期的）。
    const assistantId = nextLocalId()
    controller = new AbortController()
    set((s) => ({
      streaming: true,
      lastError: null,
      messages: [
        ...s.messages,
        {
          id: assistantId,
          role: 'assistant' as const,
          content: '',
          createdAt: Date.now(),
          streaming: true,
          ...(lane ? { agentKind: lane } : {}),
          ...(target.model ? { model: target.model } : {}),
        },
      ],
    }))
    const { handlers, finishAssistant } = createTurnHandlers(assistantId, set, get, () => assistantId, 1)
    try {
      const resp = await copilotApi.openRegenerateStream(
        sessionId,
        { from_message_id: fromMessageId, mode, ...(lane ? { agents: [lane] } : {}) },
        controller.signal,
      )
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)
      await consumeAgentStream(resp, handlers)
      finishAssistant()
    } catch {
      finishAssistant()
      if (!controller?.signal.aborted) set({ lastError: '重生成中断，请稍后重试' })
    } finally {
      controller = null
      set({ streaming: false })
      // 服务端是真相：superseded 标记、新回答的主键、来源锚点都在那边。
      // 切会话会重拉历史，所以只在用户还停在这个会话时做。
      if (get().sessionId === sessionId) await get().switchSession(sessionId)
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
      // 受理即切任务会话：徽标 + 轮询由此展开；完成通知进会话历史
      await get().switchSession(receipt.session_id)
    } catch {
      set({ lastError: '提交后台任务失败，请稍后重试' })
    }
  },
})
