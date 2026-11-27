/**
 * `store.send` 的发送流水线：守卫之后的五个阶段各成一个模块级函数。
 *
 * 从 `store/turn.ts` 拆出（`send` 单函数曾占 247 行，建会话/上传/开流/收流多个
 * await 阶段全挤在一起，既撞 450 行硬红线，也让「哪一步失败该写什么状态」混在
 * 一个函数里）。本文件只服务
 * `createTurnSlice().send`，不是公共 API：栏数与模型的决策仍在 turn.ts
 * （resolveAnswerAgents / resolveAnswerSpecs，工具栏也读同一份），由 send 传进来。
 *
 * 阶段顺序 = 副作用顺序，**不要重排**：
 * 锚点注入（buildOutgoingText）→ 建会话（ensureSession）→ 附件/引用上传并拼出站
 * （ensureOutgoing）→ 建气泡并重置轮次状态（beginAnswerTurn）→ 消费 SSE 并收尾
 * （runAnswerStream）。每个 await 之后都要重申「用户有没有切会话」：迟到结果必须
 * 丢弃（2026-10 审查 F2）。
 */

import * as copilotApi from '../api'
import {
  buildBizHintBlock,
  buildSelectionQuoteBlock,
  classifyStreamEnd,
  nextLocalId,
  splitBizHintLine,
  splitPageHintLine,
  splitQuoteBlock,
  splitRefBlocks,
} from '../domain'
import { uploadAttachmentsAndCompose } from '../outgoing'
import { seedAnswerSelectionFromNew, storeSession } from '../persistence'
import { consumeAgentStream } from '../streaming'
import { createTurnHandlers } from '../turn-handlers'
import type { AgentSpec, CopilotState, SelectionQuote, TurnStats } from '../types'
import { bumpSessionEpoch } from './session-epoch'
import type { GetState, SetState } from './slice'

type CopilotSet = SetState<CopilotState>
type CopilotGet = GetState<CopilotState>

/**
 * 出站正文：锚点 + 框选引用块（纯组装，唯一的副作用是记下已注入的页面锚点）。
 *
 * 锚点（模型据此知道自己服务谁、用户在哪个页面）：
 * - 业务范围内（详情页工作区/浮层 context）：每轮注入归属锚点——pi 的 compaction
 *   可能把首轮上下文压掉，不重复注入模型就会「失忆」反问「哪个案件」（实测发生过）；
 *   含实体 id，模型可直接调工具读绑定文件夹。
 * - 通用模式：页面变化后首条才注页面锚点（历史不刷屏）。
 */
export function buildOutgoingText(pre: CopilotState, trimmed: string, set: CopilotSet): string {
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
  return outgoingText
}

/**
 * 本轮发送归属哪个会话：无会话则先建。
 *
 * 返回 `null` = 已处理早退（建会话失败 / 建会话期间用户切走），调用方直接 return。
 * `sending` 锁与 `onQueued(false)` 都在这两条早退分支里清——锁贯穿全程，漏清一处
 * 就是永久锁。
 */
export async function ensureSession(
  /** 新会话的后端归属（本轮勾选的第一个，未勾退回部署默认；见 send 里的口径） */
  ownerKind: string,
  context: CopilotState['context'],
  get: CopilotGet,
  set: CopilotSet,
  onQueued?: (sent: boolean) => void,
): Promise<string | null> {
  // await 期间用户可能切会话/开新对话，迟到结果必须丢弃，
  // 否则会覆盖用户刚选中的会话并把消息推进去
  const startedSessionId = get().sessionId
  if (startedSessionId) return startedSessionId
  let sessionId: string
  try {
    sessionId = (await copilotApi.createSession('', context ?? undefined, ownerKind)).session_id
  } catch {
    set({ lastError: '创建会话失败，请稍后重试', sending: false })
    onQueued?.(false)
    return null
  }
  // createSession 在途期间用户已切走：不占用新会话，也不污染当前视图
  if (get().sessionId !== startedSessionId) {
    set({ sending: false })
    onQueued?.(false)
    return null
  }
  bumpSessionEpoch()
  // 建会话这一刻必须先搬家：勾选/模型是律师在「新对话」里选的，写盘落在
  // `copilot:agents:new` / `copilot:models:new`；不搬的话紧接着的 hydrate 会按
  // `<新 id>` 读到空，把刚勾的选择当场清成 0（用户看到「已选 0 个」，刷新也回不来）。
  seedAnswerSelectionFromNew(sessionId)
  set({ sessionId })
  storeSession(sessionId)
  return sessionId
}

/**
 * 附件/引用先行出站（服务端存档拿引用 id，消息里附引用块——模型用
 * read_agent_attachment(id) 读正文，base64 不进上下文），成功后清 chips。
 *
 * 返回拼好的出站正文；`null` = 已处理早退（准备失败 / 上传期间用户切走），
 * chips 保留可重试（outgoing 复用已成功回执，不重复上传）。
 */
export async function ensureOutgoing(
  sessionId: string,
  outgoingText: string,
  pendingQuote: SelectionQuote | null,
  get: CopilotGet,
  set: CopilotSet,
  onQueued?: (sent: boolean) => void,
): Promise<string | null> {
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
    return null
  }
  // 附件上传在途期间用户可能切走：迟到结果丢弃（chips 保留，回执已缓存，
  // 下次发送不重复上传），不把消息推进新选中的会话
  if (get().sessionId !== sessionId) {
    set({ sending: false })
    onQueued?.(false)
    return null
  }
  if (pendingFiles.length > 0 || pendingRefs.length > 0) set({ pendingFiles: [], pendingRefs: [] })
  if (pendingQuote) set({ pendingQuote: null })
  return outgoing.composed
}

/** 本轮建好的栏：气泡 id 表与「是不是多栏」（收尾/断流标注都要用） */
export interface AnswerTurn {
  assistantId: string
  assistantByAgent: Record<string, string>
  multiColumn: boolean
}

/**
 * 用户消息与本轮各栏的 assistant 气泡入列，并重置轮次状态。
 *
 * 单栏路径必须与多答前**完全一致**（agentKind 留空、渲染不加标签，见
 * domain/dual.groupAnswerRuns）。`onQueued(true)` 表示消息已入列、流即将开启。
 */
export function beginAnswerTurn(args: {
  composed: string
  turnAgents: string[]
  turnSpecs: AgentSpec[]
  /** 轮次统计初值（turn.ts 的 EMPTY_STATS——初值与每轮重置必须是同一份） */
  initialStats: TurnStats
  set: CopilotSet
  onQueued?: (sent: boolean) => void
}): AnswerTurn {
  const { composed, turnAgents, turnSpecs, initialStats, set, onQueued } = args
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
    turnStats: { ...initialStats, samples: [] },
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
  return { assistantId, assistantByAgent, multiColumn }
}

/**
 * 开流并消费 SSE，收尾本轮。
 *
 * `ctrl` 是 store 的模块级在途句柄（stop 用它中断）。`releaseController` 在
 * finally 里先于 `streaming=false` 调用：句柄的生命周期严格包住流的消费。
 */
export async function runAnswerStream(args: {
  ctrl: AbortController
  sessionId: string
  composed: string
  turnAgents: string[]
  turnSpecs: AgentSpec[]
  turn: AnswerTurn
  releaseController: () => void
  get: CopilotGet
  set: CopilotSet
}): Promise<void> {
  const { ctrl, sessionId, composed, turnAgents, turnSpecs, turn, releaseController, get, set } = args
  const { assistantId, assistantByAgent, multiColumn } = turn
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
  const laneIds = new Set<string>(multiColumn ? Object.values(assistantByAgent) : [assistantId])
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

  try {
    const resp = await copilotApi.openMessageStream(sessionId, composed, ctrl.signal, turnSpecs)
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
    if (ctrl.signal.aborted) {
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
    releaseController()
    set({ streaming: false, queuePosition: null })
  }
}
