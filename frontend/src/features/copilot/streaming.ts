/**
 * SSE 流消费器：读 Response.body、切帧、按事件类型分发给 handlers。
 *
 * 从 store.send 中抽出（保持 store 只做状态编排）：帧解析在 domain.ts（纯函数），
 * 这里负责 reader 生命周期与事件路由。事件契约见 types.ts / 后端 chat_service。
 * 循环读到底（done 帧后由服务端关流），调用方无需提前退出。
 */

import { agentOf, narrowCitations, parseSseEvent, runIdOf, takeSseFrames } from './domain'
import type { ErrorInput } from './domain'
import type { AgentStreamEvent, CitationRef } from './types'

type ToolCallEvent = Extract<AgentStreamEvent, { type: 'tool_call' }>
type ToolResultEvent = Extract<AgentStreamEvent, { type: 'tool_result' }>
type ApprovalEvent = Extract<AgentStreamEvent, { type: 'approval_request' }>
type QuestionEvent = Extract<AgentStreamEvent, { type: 'question_request' }>
type UiActionEvent = Extract<AgentStreamEvent, { type: 'ui_action' }>
type UiSnapshotRequestEvent = Extract<AgentStreamEvent, { type: 'ui_snapshot_request' }>

/**
 * usage 事件的归一化载荷。
 *
 * `cacheReadTokens` 是验证「提示词前缀稳定 → 命中 prompt cache」的唯一手段：
 * 它高说明前缀没变（记忆快照没漂、工具集没抖）、成本低；它低说明每轮都在
 * 重建前缀。命中率 = cacheRead / (input + cacheRead + cacheWrite)。
 */
export interface UsagePayload {
  outputTokens: number
  inputTokens: number
  cacheReadTokens: number
  cacheWriteTokens: number
}

/**
 * 「这一帧是谁产的」——多答时前端靠它把交错的事件分到各自的栏。
 *
 * 为什么带在**每个** handler 上而不是进 `StreamHandlers` 的构造参数：一帧只在
 * 帧解析那一刻知道自己的 `agent`，而 handler 是跨帧复用的。带参数的形状让
 * 「事件来自哪个 agent」跟着事件走，不会因为 handler 内部记状态而在交错流里
 * 串栏（两个 agent 的事件是交替到达的，状态一旦落到闭包里就会互相覆盖）。
 */
export interface EventOrigin {
  /** 事件里的 `agent`；缺失时按 pi（见 domain/dual.agentOf） */
  kind: string
  runId: string
}

export interface StreamHandlers {
  /** 思考增量（不计入正文） */
  onThinking(chunk: string, origin: EventOrigin): void
  /** 正文增量 */
  onDelta(chunk: string, origin: EventOrigin): void
  onToolCall(event: ToolCallEvent, origin: EventOrigin): void
  onToolResult(event: ToolResultEvent, origin: EventOrigin): void
  /** usage 事件（pi 精确计数，一轮内多段 assistant 逐次上报）
   *
   * 传结构体而不是位置参数：字段还会长（cache 已是第三个维度），
   * 位置参数每加一个就要改所有实现，且容易错位。
   */
  onUsage(usage: UsagePayload, origin: EventOrigin): void
  /**
   * 审批请求。
   *
   * `origin` 不可省：多答时两栏可能同时要审批，卡上不写来源，律师根本分不清
   * 「这是哪条回答要用我的库表」。注意 `origin.kind` 缺失时会回落 pi（为了事件
   * 路由），**不能**拿它当栏来源——单栏/旧后端的「没有来源」由 handler 按本轮
   * 栏数（`columnCount`）判断并记空串。
   */
  onApproval(event: ApprovalEvent, origin: EventOrigin): void
  /**
   * 模型反问（结构化提问）。
   *
   * 可选实现，但**不实现就等于把提问丢掉**：后端会阻塞等 180s，然后按假设
   * 继续——法律场景里那等于「AI 自己编了个事实接着干」。所以真正开流的 store
   * 必须实现它。`questions` 是后端归一化后的自由形状（字段见
   * services/question.py），由 domain/question.normalizeQuestions 宽容解析。
   */
  onQuestion?(event: QuestionEvent, origin: EventOrigin): void
  /**
   * 界面动作下发（`ui_action`）。
   *
   * **可选实现，但不实现就等于把动作丢掉**：后端不会因为前端没接住而报错或重发
   * （T1 是单向指令），于是模型照旧对律师说「已帮你切过去」，页面一动不动，而日志
   * 里连一条错误都没有。2026-11-27 今天就踩了这一次：`createUiActionHandler` 返回的
   * 键名是事件名 `ui_action`，而这里的分发是写死的 `switch (event.type)`，没有
   * `case 'ui_action'`，帧直接落进 `default: break`——**编译期不报错**（`turn-handlers`
   * 用 spread 合并，TS 的 excess-property 检查对 spread 不生效）。
   * 因此开关两侧必须成对改：本接口加成员 + switch 加 case + 回归用例
   * `streaming.ui-action.test.ts` 钉死。
   *
   * 为什么带 `origin`：多栏并答时两栏都可能下发动动作，横幅要能标清「是哪一栏在动」
   * （单栏时 handler 按 `columnCount` 决定是否显示来源）。
   */
  onUiAction?(event: UiActionEvent, origin: EventOrigin): void
  /**
   * 页面状态快照请求（`ui_snapshot_request`）—— AI 想知道「现在页面上是什么」。
   *
   * 与 `onUiAction` 同一类开关：**可选实现，但不实现就等于把请求丢掉**，而后端只等 3 秒
   * （超时按「没问到」继续，不会重试），于是模型只能改问律师、白丢一次省往返的机会。
   * 2026-11-27 的 P0-1 就是「只加 handler 工厂、忘了 switch 的 case」，帧被静默丢弃。
   * 所以开关两侧必须成对改：本接口加成员 + switch 加 case + `streaming.ui-snapshot.test.ts`。
   */
  onUiSnapshotRequest?(event: UiSnapshotRequestEvent, origin: EventOrigin): void
  /**
   * 引用表增量（逐句溯源）。
   *
   * 一轮内可多次到达（后端按检索/引用产生顺序分段推），调用方必须**追加合并**而
   * 不是替换。载荷已是收窄后的 `CitationRef`（snake_case → camelCase 只在
   * domain/knowledge.narrowCitations 一处做）。可选实现：不实现就等于把溯源丢掉
   * ——正文里的 `[Kn]` 仍会渲染成纯文本，只是点不开。
   *
   * `origin` 不可省：多答时两栏各有自己的引用，写死主栏会把 A 栏引的材料挂到
   * B 栏的回答下面（点开的那份不是那句话的出处）。
   */
  onCitations?(citations: CitationRef[], origin: EventOrigin): void
  /** 排队事件：前方名次（1 起，含自己在队列中的位置） */
  onQueued(position: number): void
  /** 上下文压缩进行/完成（自动压缩原本无声，律师会以为 AI「失忆」） */
  onCompaction(phase: 'start' | 'end'): void
  /** 首个推进事件（delta/thinking/tool_call/error/done）：清掉排队提示 */
  onProgress(): void
  /**
   * 后端降级：本轮只跑了主后端（aux 席位已满），`reason` 是给律师看的一句话。
   *
   * 可选实现：不关心降级的调用方（测试替身、单后端路径）不必提供。不提供的话，
   * 被丢下的那几栏会一直留在 streaming 状态（光标转不停、done 永远不来），所以
   * 真正开多栏的 store 必须实现它。
   */
  onDegraded?(reason: string): void
  /**
   * 后端 `error` 帧。
   *
   * 传**整个结构体**（`message` + `code` / `scope` / `detail`）而不是光一个
   * `message`：后端从 2026-10 起就在帧上给了这三件套（`sse_types.py` 的
   * `ErrorMessage`），而这里曾经只转发 `event.message`，把 `code` / `scope` /
   * `detail` 全扔了。后果链：`lastError` 变成裸文案 → `classifyError` 拿不到
   * code → 一律落 `unknown` → 律师看到「未知错误｜请联系管理员」，而诊断里
   * 连 `detail.session_id` 都没有（2026-11-24 实测：`session_not_found` 就是
   * 这么被报成 unknown 的）。写方直接交给 `encodeError` 即可（见 lane-lifecycle）。
   */
  onError(err: ErrorInput, origin: EventOrigin): void
  /**
   * 某一方跑完。
   *
   * `origin` 不可省：双答时两个后端**各自**发 done（后端保证整轮只有一个
   * done 事件，但那是「会话级」的；每栏仍需要知道「我这栏跑完了」）。
   * 不收 origin 的话，先完成的那栏会让 `finishAssistant()` 把另一栏一起收掉
   * ——另一栏后续的 delta 无处可去，界面上就是「(无内容)」。
   */
  onDone(context: { used: number | null; total: number | null } | undefined, origin: EventOrigin): void
  /**
   * 流到了 EOF——**不管有没有 done**。`sawDone=false` 就是「这是断流」。
   *
   * 与返回值分工：返回值是给**调用方**的收尾结论（store 据此按栏标截断），本回调
   * 是给 **handler 自己**的：有些状态只能靠「又一个事件」退场（如 `compaction end`
   * 才清的 `compacting`），流被掐断时它就永远转下去了。可选项。
   */
  onStreamEnd?(outcome: StreamOutcome): void
}

/**
 * 流的收尾结论。
 *
 * `sawDone=false` 是**可观测的异常**：连接被掐断时 `reader.read()` 只会正常
 * 返回 `done:true`，看上去和「服务端跑完了」一模一样——不区分就会把断流记成
 * 正常完成（红队审查 R1）。
 */
export interface StreamOutcome {
  /** 是否收到过 done 帧（每栏各发一条，多答时 ≥1 即算正常收尾） */
  sawDone: boolean
  /**
   * 真正收到 done 的栏（只认 done 帧里**显式**的 `agent`）。
   *
   * 全局 `sawDone` 回答不了「**哪一栏**跑完了」：三栏只到 1 个 done 时它照样是
   * `true`，另两栏就此静默留空（真实事故：界面上两个空栏头，看起来像「AI 回答了
   * 但内容丢了」）。按栏记账后，收尾时才能把缺的栏标「已中断」（判定见
   * domain/stream-guard.classifyStreamEnd）。
   */
  doneKinds: string[]
  /** 收到过「没写来源」的会话级 done（旧后端/单栏：等于整轮都收尾了） */
  sessionLevelDone: boolean
}

/**
 * done 帧里**显式**标注的来源；空串 = 这帧没写 `agent`。
 *
 * 不能用 `agentOf`：它对缺省值回落到 `pi`（多答前只有 pi 在跑），拿来记「谁
 * 跑完了」会把一条没标来源的 done 记成「pi 那一栏跑完了」——多答里 pi 不在第一栏
 * 时，真正跑完的那栏反而会被标成缺 done。
 *
 * 也不用帧里的 `agents`：那是本轮的**全量**栏清单，第一条 done 就带全家，拿它当
 * 「谁跑完了」会让缺 done 的栏永远不被发现——正好是那个静默空栏 bug。
 */
function explicitAgentOf(event: object): string {
  return ((event as { agent?: string }).agent ?? '').trim()
}

/** 消费一条 agent SSE 流，逐帧分发；流读尽或中途异常时返回/抛出。 */
export async function consumeAgentStream(resp: Response, h: StreamHandlers): Promise<StreamOutcome> {
  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  /** 收到 done 的栏（按显式 `agent`）；会话级 done 另记一个开关 */
  const doneKinds = new Set<string>()
  let sessionLevelDone = false
  for (;;) {
    const { done, value } = await reader.read()
    let frames: string[]
    if (done) {
      // EOF：缓冲区里的残渣要再解析一轮。`decoder.decode()` 无参调用把流式解码器
      // 里攒着的半个多字节字符冲出来（中文被切在 chunk 边界上时不冲就是乱码）。
      //
      // 为什么必须做：服务端写完最后一帧常常直接关流、不补 `\n\n`，那个尾巴上
      // 可能正好是 done（丢了就把正常轮次记成断流），也可能是最后一截正文或一次
      // usage（丢了就是可见的数据丢失）。
      buffer += decoder.decode()
      const tail = takeSseFrames(buffer)
      frames = tail.frames
      const leftover = tail.rest.trim()
      // 剩下的是没有空行结尾的那一帧（或半帧）：是完整 JSON 就照发，半帧由
      // parseSseEvent 的 JSON.parse 兜住（容错返回 null，流不当异常）
      if (leftover) frames = [...frames, leftover]
    } else {
      buffer += decoder.decode(value, { stream: true })
      const part = takeSseFrames(buffer)
      buffer = part.rest
      frames = part.frames
    }
    for (const frame of frames) {
      const event = parseSseEvent(frame)
      if (!event) continue
      // 每帧自己的来源：双答时两个 agent 的事件交替到达，绝不能记在 handler 上
      const origin: EventOrigin = { kind: agentOf(event), runId: runIdOf(event) }
      switch (event.type) {
        case 'thinking':
          h.onProgress()
          h.onThinking(event.content, origin)
          break
        case 'delta':
          h.onProgress()
          h.onDelta(event.content, origin)
          break
        case 'citations':
          // 入站引用（逐句溯源）：一轮内可多次到达，每次只带新增那几条。
          // 收窄只有一处（narrowCitations），实时与历史回放共用同一判据。
          h.onCitations?.(narrowCitations(event.citations), origin)
          break
        case 'tool_call':
          h.onProgress()
          h.onToolCall(event, origin)
          break
        case 'tool_result':
          h.onToolResult(event, origin)
          break
        case 'usage':
          // origin 必须跟着走：多答要按栏归集，丢了来源就只能全算在主栏上
          h.onUsage(
            {
              outputTokens: event.output_tokens,
              inputTokens: event.input_tokens ?? 0,
              cacheReadTokens: event.cache_read_tokens ?? 0,
              cacheWriteTokens: event.cache_write_tokens ?? 0,
            },
            origin,
          )
          break
        case 'approval_request':
          h.onApproval(event, origin)
          break
        case 'question_request':
          // 提问不阻断流：卡片与审批同层并列渲染，模型在服务端等回答
          // （超时即按假设继续，前端仍可补答）
          h.onProgress()
          h.onQuestion?.(event, origin)
          break
        case 'ui_action':
          // 界面动作不是工具结果：不进转录、不落 tool 行，只交给执行层就地生效
          // （理由见 handlers/ui-action-handler.ts 文件头）。
          h.onProgress()
          h.onUiAction?.(event, origin)
          break
        case 'ui_snapshot_request':
          // AI 问「现在页面上是什么」：读页面注册表并回传（超时不是错误，后端按没问到继续）。
          // 与 onUiAction 成对：接口成员 + 这里的 case + streaming.ui-snapshot.test.ts 三件套。
          h.onProgress()
          h.onUiSnapshotRequest?.(event, origin)
          break
        case 'compaction':
          h.onCompaction(event.phase)
          break
        case 'activity':
          // queued 时带 position（前方名次）；thinking 不入转录；
          // degraded 表示多答被降级成只跑主后端（aux 席位已满）
          if (event.status === 'queued' && typeof event.position === 'number') {
            h.onQueued(event.position)
          } else if (event.status === 'degraded') {
            h.onDegraded?.(event.reason ?? '本轮只跑了主后端')
          }
          break
        case 'error':
          // 每个失败方只发一条（后端保证不堆两条），这里按来源挂到对应栏。
          // 四件套整包转发——少传一个字段，前端就少一条可执行建议（见 onError 注释）。
          h.onProgress()
          h.onError(
            { message: event.message, code: event.code, scope: event.scope, detail: event.detail },
            origin,
          )
          break
        case 'done': {
          // 按栏记账（只认显式 agent）：收尾时要能回答「哪一栏没等到 done」
          const who = explicitAgentOf(event)
          if (who) doneKinds.add(who)
          else sessionLevelDone = true
          h.onProgress()
          // 水位字段可选：旧后端 / pi 未上报时 undefined，前端隐藏水位显示
          h.onDone(
            event.context_used_tokens === undefined && event.context_total_tokens === undefined
              ? undefined
              : { used: event.context_used_tokens ?? null, total: event.context_total_tokens ?? null },
            origin,
          )
          break
        }
        default:
          break // meta / activity(thinking) 不入转录
      }
    }
    // EOF 这一轮的 frames 已经分发完：必须跳出，否则 read() 会一直返回 done:true
    // 永不结束（缓冲区残渣会被反复重新分发，表现为整轮挂死）
    if (done) break
  }

  const outcome: StreamOutcome = {
    sawDone: sessionLevelDone || doneKinds.size > 0,
    doneKinds: [...doneKinds],
    sessionLevelDone,
  }
  // 两条通道，各管各的：回调给 handler 清瞬态（此刻仍在读循环的上下文里），返回值
  // 给 store 做收尾判定。store **不能**在回调里收尾：它还要 finishAssistant() 清
  // streaming，两处写同一帧状态会互相覆盖。
  h.onStreamEnd?.(outcome)
  return outcome
}
