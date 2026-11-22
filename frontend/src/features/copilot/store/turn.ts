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
  emptyTurnStats,
  nextLocalId,
  splitBizHintLine,
  splitPageHintLine,
  splitQuoteBlock,
  splitRefBlocks,
} from '../domain'
import { MAX_ANSWERS, classifyStreamEnd, ratableMessageId } from '../domain'
import { uploadAttachmentsAndCompose } from '../outgoing'
import { storeSession } from '../persistence'
import { consumeAgentStream } from '../streaming'
import { createTurnHandlers } from '../turn-handlers'
import type { AgentSpec, CopilotState, TurnStats } from '../types'
import { resolveCapabilities } from './backends'
import { bumpSessionEpoch } from './session-epoch'
import type { Slice } from './slice'

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
 * 归属本 slice：只有 send 创建/清除它、只有 stop 消费它。decide() 等动作
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
      // 新会话归属 = 本轮勾选的第一个（顺序 = 栏的左右顺序）；未勾 / 全不可用退回
      // selectedAgentKind（部署默认）。❗必须用**过滤后**的清单（见 resolveAnswerAgents）：
      // 直接取 answerAgents[0] 会让「勾了一个缺 SDK 的后端」变成会话归属，而它不在本轮。
      const ownerKind = resolveAnswerAgents(pre)[0] || pre.selectedAgentKind
      try {
        sessionId = (await copilotApi.createSession('', get().context ?? undefined, ownerKind)).session_id
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
    // 待发 `@` 引用由这里下发（outgoing 不反向 import store，见其文件头）
    const pendingMentions = get().pendingMentions
    if (pendingFiles.length > 0 || pendingRefs.length > 0) set({ uploadingAttachments: true })
    const outgoing = await uploadAttachmentsAndCompose(
      sessionId,
      outgoingText,
      pendingFiles,
      pendingRefs,
      pendingMentions,
    )
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

    // 本轮要几栏：选中的 agent 清单（过滤不可用 / 截到上限后才是真实栏数）。单栏路径
    // 必须与多答前**完全一致**（agentKind 留空、渲染不加标签，见 domain/dual.groupAnswerRuns）。
    const turnAgents = resolveAnswerAgents(pre)
    // 每栏带模型（缺省不带 = 平台默认）；顺序与 turnAgents 逐一对应
    const turnSpecs = resolveAnswerSpecs(pre)
    const multiColumn = turnAgents.length > 1
    const assistantId = nextLocalId()
    // 每个 agent 一栏：id 先算好，气泡与事件路由共用同一份——两处各 nextLocalId()
    // 会造出「气泡挂在 A 的 id、事件写进 B 的 id」这种只差一个字难以发现的错配。
    const assistantByAgent: Record<string, string> = multiColumn
      ? Object.fromEntries(turnAgents.map((kind, i) => [kind, i === 0 ? assistantId : nextLocalId()]))
      : {}
    // 各栏点名的模型：气泡先带上（后端事件不带 model，不在这里记就永远丢了）。
    // 单栏不记——单栏不显示「· 模型」（见 MultiAnswers）。
    const modelByAgent: Record<string, string> = multiColumn
      ? Object.fromEntries(turnSpecs.flatMap((spec) => (spec.model ? [[spec.kind, spec.model]] : [])))
      : {}
    // 与历史回放同一解析：本地即时渲染也把页面/业务锚点、引用块还原成 chip，两侧不漂移
    const { pageHint, body: noHint } = splitPageHintLine(composed)
    const { bizHint, body: noBiz } = splitBizHintLine(noHint)
    const { refs, body: noRefs } = splitRefBlocks(noBiz)
    const { quote, body } = splitQuoteBlock(noRefs)
    // 实时气泡也要有时间戳：`createdAt` 原先只有历史回放填，于是「刚发出去的这条」
    // 下面没有时间、刷新一次才出现——同一份数据两个样，律师会以为时间戳是随机的。
    const sentAt = Date.now()
    set((s) => ({
      messages: [
        ...s.messages,
        {
          id: nextLocalId(),
          role: 'user',
          content: body,
          createdAt: sentAt,
          ...(pageHint ? { pageHint } : {}),
          ...(bizHint ? { bizHint } : {}),
          ...(refs.length ? { refs } : {}),
          ...(quote ? { quote } : {}),
        },
        // 单后端：一条不带 agentKind 的气泡（与历史渲染口径一致：空串 = 旧行为）
        ...(multiColumn
          ? turnAgents.map((kind) => ({
              id: assistantByAgent[kind]!,
              role: 'assistant' as const,
              content: '',
              createdAt: sentAt,
              streaming: true,
              agentKind: kind,
              ...(modelByAgent[kind] ? { model: modelByAgent[kind] } : {}),
            }))
          : [{ id: assistantId, role: 'assistant' as const, content: '', createdAt: sentAt, streaming: true }]),
      ],
      // 本会话里**已挂起的他线待审卡不能因为发一句话就消失**：它往往来自后台
      // 任务（无人可问时挂起两小时），律师回来先发一条消息再想去批，卡已经没了。
      // 在线卡（本轮正在等的那个）才随本轮重置——旧的在线卡早已过 300s 窗口。
      approvals: s.approvals.filter((a) => a.offline && !a.decided),
      streaming: true,
      // 消息已入列、流已开：置忙交给 streaming，sending 在此解除
      sending: false,
      queuePosition: null,
      queuedSteers: [],
      turnStats: { ...EMPTY_STATS, samples: [] },
      // 分栏账按轮重置：上一轮的栏不该出现在本轮栏头。
      //
      // **不要改成「保留上一轮并标记为历史」**：栏头 chip 是按 kind 直取的
      // （见 LaneUsageChip），留着旧键就是让本轮的 pi 栏挂着上一轮 pi 的速度与
      // token 数——那正是「数字看着像真的、但错了」的一类 bug。
      //
      // 历史轮次的用量因此**不在这里保留**，唯一正确的位置是落库的消息 metadata
      // （`usage_by_lane` + `ttft_ms`，由 domain/usage 的 `laneUsageFromMetadata`
      // 收窄成 LaneUsage，由 transcript 回放时挂到气泡上）。也就是说：刷新后要
      // 看见历史栏用量，需要「按轮/按消息存放的结构」——那属于 types.ts /
      // state-types.ts，不在本文件的口径内，别在这里糊一个近似实现。
      turnStatsByLane: {},
    }))
    onQueued?.(true)

    // 本轮的 SSE → 状态更新集中在 turn-handlers（正文/思考/工具行/审批/排队/统计）。
    // 多栏时按事件里的 agent 分到各自气泡：路由表的键是 kind，缺 agent 的事件
    // 落到第一条（主栏）——鉴于是「旧口径」且多答前只有一条气泡。
    const { handlers, finishAssistant } = createTurnHandlers(
      assistantId,
      set,
      get,
      (kind) => assistantByAgent[kind] ?? assistantId,
      turnAgents.length,
    )

    // 本轮有哪些气泡：断流时要精确标它们（不能按 `streaming` 扫全场，
    // 否则会误伤下一轮刚开的气泡）
    const laneIds = new Set<string>(
      multiColumn ? Object.values(assistantByAgent) : [assistantId],
    )
    /**
     * 把本轮各栏标成「已中断」。
     *
     * 不重拉历史是本轮改造的重点（红队审查 C2）：`switchSession` 会整段替换
     * `messages`，把刚流出的正文、分栏账、未落库的栏全部冲掉——用户看到的是
     * 「我按了停止，答案就没了」。服务端那边确实落了 truncated，但它要下一次
     * 打开会话才看得到；眼前这一屏必须留着。
     */
    const markInterrupted = (ids: Set<string>) => {
      set((s) => ({
        messages: s.messages.map((m) =>
          // 已经标 `failed` 的栏有自己的「本轮未做」：再叠一个「已中断」会让一栏上
          // 挂两个徽标，读不出到底发生了什么（降级 + 断流同时发生时就会这样）
          m.role === 'assistant' && ids.has(m.id) && !m.failed
            ? { ...m, streaming: false, truncated: true }
            : m,
        ),
      }))
    }
    /** 栏 kind → 气泡 id（与 turn-handlers 的路由表同源） */
    const laneIdOf = (kind: string) => assistantByAgent[kind] ?? assistantId

    controller = new AbortController()
    try {
      const resp = await copilotApi.openMessageStream(sessionId, composed, controller.signal, turnSpecs)
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)
      const outcome = await consumeAgentStream(resp, handlers)
      finishAssistant()
      set((s) => ({ turnStats: { ...s.turnStats, doneAt: s.turnStats.doneAt ?? Date.now() } }))
      // 收尾：连接正常结束但没收到 done = 上游被掐断（反代超时/服务重启）。
      // 「是否已报过错」与「是否截断」是两个独立事实（原先 `lastError !== null` 会拦住
      // 标截断）：先降级/报错、再断流时，那句更具体的错误不能把「这几栏没等到 done」
      // 一起吃掉——律师只看到一句解释，却看不到「回答可能不完整」。
      //
      // 单栏传空栏清单：单栏事件照样带后端的 agent，拿它比对会误判成缺 done。
      const verdict = classifyStreamEnd({
        lanes: multiColumn ? turnAgents : [],
        doneKinds: outcome.doneKinds,
        sessionLevelDone: outcome.sessionLevelDone,
      })
      // 只标缺 done 的那几栏（不能把跑完的栏也标中断）；单栏归「整轮气泡」的旧口径
      if (verdict.truncated) {
        markInterrupted(
          verdict.missingLanes.length > 0 ? new Set(verdict.missingLanes.map(laneIdOf)) : laneIds,
        )
      }
      // 更具体的错误优先：已说了「对比执行位已满」，再叠一句「连接提前结束」只会绕晕人
      const notice = verdict.notice
      if (notice) set((s) => ({ lastError: s.lastError ?? notice }))
    } catch {
      finishAssistant()
      const aborted = controller?.signal.aborted === true
      if (aborted) {
        // 主动停止：保留已流出正文与统计，只标截断（服务端已落 truncated）
        markInterrupted(laneIds)
      } else {
        // 真失败（网络断/HTTP 错）：重拉历史对齐服务端落库结果，再提示
        if (get().sessionId) {
          await get().switchSession(get().sessionId)
        }
        set({ lastError: '连接中断，请重试' })
      }
    } finally {
      controller = null
      set({ streaming: false, queuePosition: null })
    }
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
