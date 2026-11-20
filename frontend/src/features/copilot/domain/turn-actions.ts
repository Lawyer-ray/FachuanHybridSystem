/**
 * 轮次级「还能对这个回答做什么」的纯判据（不接 UI）。
 *
 * 为什么单独一个文件、且**只写判据不写按钮**：这两件事都需要后端能力才能真
 * 落地（见下方两个导出函数的说明），现在接上按钮只会造出「可点但必然失败」
 * 的假可用路径——`ErrorNotice` 里「不做重试」的理由同样适用：`send()` 会二次
 * 注入业务锚点，前端拿不到「本轮已组装好的出站正文」，直接重发会把锚点写两遍。
 *
 * 判据先落地的好处是：等后端端点就绪时，接线只剩「把结果喂给按钮」一步，
 * 而「什么状态可继续 / 可重生成」的语义现在就能被单测锁死，不会两边各猜一套。
 *
 * 与后端契约对齐的事实（`backend/apps/agent/sse_types.py:29-40`）：
 * `finish_reason ∈ {ok, degraded, error, cancelled}`，一份枚举两种载体——
 * SSE 的 `done` 只可能取到前三个（客户端断开时生成器已被关闭，没有通道发
 * `done`），`cancelled` **只出现在落库 metadata 里**。所以「这轮是不是被打断」
 * 必须两路都看：实时路径看 `truncated`，历史回放看 `metadata.finish_reason`。
 */

/** 后端 `FinishReason` 的前端镜像（见文件头注释的同一份枚举） */
export type FinishReason = 'ok' | 'degraded' | 'error' | 'cancelled'

/**
 * 可继续（续写/重跑后半段）的落库原因：被取消或出错。
 *
 * 为什么这两个：这两种终态意味着「用户想要的完整回答**没有**产生」，续写有意义。
 * `ok` 是正常结束（再继续只会得到画蛇添足的重复）；`degraded` 指多答里**别的栏**
 * 失败了、这一栏自己是好的，也不该补写。
 */
const CONTINUABLE_REASONS: ReadonlySet<string> = new Set<FinishReason>(['cancelled', 'error'])

/**
 * `canContinue` 的输入形状。
 *
 * 三个键都可选是刻意的：
 * - 旧数据（引入 `finish_reason` 之前的行）只有 `metadata.truncated`；
 * - 新数据两者都有；
 * - 实时气泡只有 `truncated`（停止/断连时本地置位，见 store/turn.ts）。
 *
 * `ChatMessage` 可直接传进来（它的 `truncated?: boolean` 满足本形状）；
 * `finishReason` / `finish_reason` 需要调用方从 `metadata` 取——**目前还没有
 * 任何地方映射它**（`domain/transcript.ts` 只映射了 `truncated` 与 `model`）。
 * 接线前必须先补那一行映射，否则历史回放永远只看得到 truncated 这一路。
 */
export interface ContinuableMessage {
  /** 服务端 `metadata.truncated` 透传：被停止或断连截断 */
  truncated?: boolean
  /** 应用形状（驼峰）：聊天消息上的落库终态 */
  finishReason?: string | null
  /** 落库 `metadata` 原样传入时的蛇形键（后端契约拼写，别在前端改名） */
  finish_reason?: string | null
}

/** 取终态（驼峰优先，其次后端原样的蛇形键；都没有 → undefined） */
function finishReasonOf(source: ContinuableMessage): string | undefined {
  const reason = source.finishReason ?? source.finish_reason
  return typeof reason === 'string' && reason ? reason : undefined
}

/**
 * 这条回答还能不能「继续」（把被中断的答案往下写）。
 *
 * 判据：`truncated === true` **或** 落库终态 ∈ {cancelled, error}。
 *
 * 两路都看是硬要求：旧数据只有 `truncated`（那时后端还写 `finish_reason`），
 * 只看 `finish_reason` 会让所有历史行退化；而只看 `truncated` 又会漏掉
 * 「生成器被关闭、根本没走到置 truncated 那一刻」的 cancelled 行。
 *
 * 未知/空输入一律 false：不可用可以写出原因，误判可用则会「点了没反应」。
 */
export function canContinue(message: ContinuableMessage | null | undefined): boolean {
  if (!message) return false
  if (message.truncated === true) return true
  const reason = finishReasonOf(message)
  return reason !== undefined && CONTINUABLE_REASONS.has(reason)
}

/**
 * `canRegenerate` 的输入形状：**一栏**（多答时一轮里的一条 assistant 消息）。
 *
 * 用消息而不是「轮次」：多答一轮里有 2~4 栏，各栏的终态由各自的 `done` 决定
 * （`mergeAgentAnswers` 把每栏合成一条后，`streaming` / `failed` 就挂在它身上）。
 * 也接受显式的 `ended`，给将来「按轮记账」的调用方留出口。
 */
export interface RegenerableLane extends ContinuableMessage {
  /** 这一栏是否已结束（由 done / 本地收尾置位）。缺省时按 `streaming === false` 推 */
  ended?: boolean
  /** 这一栏还在流式接收 */
  streaming?: boolean
  /** 这一栏本轮没跑成（多答降级：界面显示「本轮未做」） */
  failed?: boolean
}

/**
 * 这一栏还能不能「重生成一个更好的回答」。
 *
 * 判据：**已结束且非失败**。
 * - 还在流（`streaming`）→ 不能：按钮该是「停止」而不是「重生成」；
 * - 失败栏（`failed`）→ 不能：那是本轮没跑起来，要的是「整轮再来一次」，
 *   不是让一个没有正文的栏「重生成」；
 * - 终态是 `error` / `cancelled` → 不能（同上：这两态归 {@link canContinue} 管）；
 * - `degraded`（多答里别栏失败）→ 可以：这一栏自己是有正常回答的。
 *
 * 「已结束」的推定刻意保守：`ended` 与 `streaming` 都没给时返回 **false**——
 * 状态未知时宁可不给按钮，也不要在半途的栏上显示一个会打断/重复计费的动作。
 */
export function canRegenerate(lane: RegenerableLane | null | undefined): boolean {
  if (!lane) return false
  if (lane.streaming === true) return false
  if (lane.failed === true) return false

  const ended = lane.ended === true || (lane.ended === undefined && lane.streaming === false)
  if (!ended) return false

  const reason = finishReasonOf(lane)
  if (reason === 'error' || reason === 'cancelled') return false
  return true
}
