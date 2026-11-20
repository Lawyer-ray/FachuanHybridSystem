/**
 * 错误分类（纯函数）：把 store 里那句 `lastError` 翻译成「是什么 / 要不要管 /
 * 下一步点哪个」。
 *
 * ## 为什么从「按文案」改成 code-first
 *
 * 第一版（4f248db9）只能按中文文案 `includes` 归类：那时后端 `error` 事件只有一个
 * `message`，文案是唯一抓手。代价是这张映射表的正确性依赖后端文案**一字不改**——
 * 后端把「请稍后再试」写成「请稍后重试」，`includes` 就静默落空，用户看到的是
 * 「未知错误」+ 一句没用的建议，而且**没有任何测试会红**（前端的 KNOWN 表和后端的
 * 文案从来不在同一份代码里，谁改都不会被对方的门禁拦住）。
 *
 * 后端现在在 `error` 事件上给了 `code` / `scope` / `detail`（apps/agent/sse_types.py）。
 * 于是本文件改成 **code 优先、文案兜底**：
 *
 * 0. `code` 命中 {@link CODE_TABLE} → 严重度/建议/动作按钮全由 code 决定
 * 1. `code` 缺失或认不出来（旧后端、或后端加了新 code）→ 回落 {@link KNOWN} 文案表。
 *    这张表**不能删**：灰度/回滚期间线上仍跑着只发文案的后端，它是那边唯一的分类手段。
 * 2. 都不中 → `unknown`，且**绝不抛**。前端比后端旧是常态（前端有缓存、后端先上线），
 *    遇到没见过的 code 必须降级成「未知但诊断可复制」，不能整块 UI 白屏。
 *
 * ## 结构化字段怎么进到前端
 *
 * store 的 `lastError` 目前是 `string`（`state-types.ts` 的契约不归本文件管，没动它）。
 * 所以结构化字段用 {@link encodeError} 编进同一个字符串，{@link classifyError} 自己
 * 拆回来。写入方只需把 `set({ lastError: msg })` 换成
 * `set({ lastError: encodeError({ code, message, scope, detail }) })`；没改造的旧
 * 写法（纯文案）行为完全不变，连 MessageList 的滚动依赖都不用动。
 */

import { KNOWN } from './error-copy'
import {
  CODE_TABLE,
  normalizeErrorCode,
  type ErrorCode,
  type ErrorKind,
  type ErrorSeverity,
} from './error-codes'

/**
 * code 类型仍从本模块出口：barrel `domain/index.ts` 只有 `export * from './error'`，
 * 那份出口表不归本文件维护（多 agent 并行期间谁都在改它），所以拆文件时把类型在
 * 这里转出去，`@/features/copilot/domain` 的对外签名一个字都没变。
 */
export type { ErrorCode, ErrorKind, ErrorSeverity } from './error-codes'

/** 结构化入参：后端 error 事件的三件套 + 已经渲染好的文案 */
export interface ErrorInput {
  code?: string
  message: string
  /** 出错范围（后端给的 `scope`，例如 `agent` / `attachment` / `compact`） */
  scope?: string
  /**
   * 机器可读细节。律师拿不准时要靠它说清「哪个后端、哪个模型、还能等几秒」，
   * 所以它必须能落进「诊断」文本（见 {@link diagnosticsOf}）。
   */
  detail?: Record<string, unknown>
}

export interface ClassifiedError {
  /** 归一化后的 code：一定是 {@link ErrorCode} 之一（未知折成 `unknown`） */
  code: ErrorCode
  /** 后端原样 code；与 `code` 不同时进诊断（支持人员才知道是哪个新分类） */
  rawCode: string
  kind: ErrorKind
  severity: ErrorSeverity
  /** 展示文案（已剥掉多答前缀） */
  message: string
  /** 多答时是哪一栏出的错（`pi：xxx` 的前缀）；单栏为空串 */
  lane: string
  /** 一句话建议动作（人话，不是按钮） */
  hint: string
  /** 律师可以原样再发一次吗（true 时显示「可原样重发」标记） */
  resendable: boolean
  scope?: string
  detail?: Record<string, unknown>
  /** 同类错误合并的次数（1 = 只有这一条）；见 {@link mergeError} */
  repeat: number
}

/**
 * 多答时错误行带 `agent：` 前缀（`pi：xxx`）。归类前剥掉，才能命中已知文案；
 * 剥掉的来源单独返回，用于提示「是哪一栏出错」。
 */
export function splitLanePrefix(raw: string): { lane: string; body: string } {
  const m = /^([\w.-]{1,24})：([\s\S]+)$/.exec(raw.trim())
  if (!m) return { lane: '', body: raw.trim() }
  return { lane: m[1]!, body: m[2]!.trim() }
}

/**
 * 结构化字段的字符串封装分隔符。用 `\u0001`（SOH）而不是 `|` / `::`：
 * 后者会出现在正常文案和 JSON 里，`lastIndexOf` 才能安全定位；且它不可能被用户
 * 手打出来，也不会在复制/日志里伪装成可见字符。
 */
const ENVELOPE_MARK = '\u0001copilot-error:'

/** 把结构化错误编成一个 `lastError` 字符串（store 只需存字符串，不必改状态形状） */
export function encodeError(input: ErrorInput): string {
  const meta: Record<string, unknown> = {}
  if (input.code) meta.code = input.code
  if (input.scope) meta.scope = input.scope
  if (input.detail && Object.keys(input.detail).length > 0) meta.detail = input.detail
  if (Object.keys(meta).length === 0) return input.message
  return `${input.message}${ENVELOPE_MARK}${JSON.stringify(meta)}`
}

/**
 * `encodeError` 的逆运算。任何解析失败都退化成「这就是一段纯文案」——
 * 宁可少一条 detail，也不能因为后端塞了个坏 JSON 就把整条错误吞掉（用户会以为
 * 什么都没发生）。
 */
export function splitErrorEnvelope(raw: string): ErrorInput {
  const at = raw.lastIndexOf(ENVELOPE_MARK)
  if (at < 0) return { message: raw }
  const message = raw.slice(0, at)
  try {
    const meta: unknown = JSON.parse(raw.slice(at + ENVELOPE_MARK.length))
    if (!meta || typeof meta !== 'object' || Array.isArray(meta)) return { message }
    const m = meta as Record<string, unknown>
    return {
      message,
      code: typeof m.code === 'string' ? m.code : undefined,
      scope: typeof m.scope === 'string' ? m.scope : undefined,
      detail: isPlainObject(m.detail) ? m.detail : undefined,
    }
  } catch {
    return { message }
  }
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

function matchKnown(body: string) {
  for (const known of KNOWN) {
    if (body.includes(known.match)) return known
  }
  return null
}

/**
 * 归类一条错误；空值返回 null（调用方据此不渲染）。
 *
 * 入参可以是纯文案（旧路径：`classifyError(lastError)`，内部会自动拆 envelope），
 * 也可以是后端事件的结构化三件套。
 */
export function classifyError(input: string | ErrorInput | null | undefined): ClassifiedError | null {
  if (!input) return null
  const src: ErrorInput = typeof input === 'string' ? splitErrorEnvelope(input) : input
  const rawMessage = typeof src.message === 'string' ? src.message : ''
  const { lane, body } = splitLanePrefix(rawMessage)
  // 没有正文就没什么可展示的（后端保证 error 事件带 message；真空了就当作无错误）
  if (!body) return null

  const { code, rawCode } = normalizeErrorCode(src.code)
  const detail = isPlainObject(src.detail) ? src.detail : undefined
  const scope = typeof src.scope === 'string' && src.scope ? src.scope : undefined
  const base = { rawCode, message: body, lane, scope, detail, repeat: 1 }

  // ① code 命中 → 以 code 为准（文案只作为展示原文，不再参与分类）
  const byCode = code === 'unknown' ? null : CODE_TABLE[code]
  if (byCode) {
    return { ...base, code, kind: byCode.kind, severity: byCode.severity, hint: byCode.hint, resendable: byCode.resendable }
  }

  // ② code 缺失/认不出来 → 文案兜底（旧后端唯一的分类手段；后端加了新 code 时也能救）
  const byText = matchKnown(body)
  if (byText) {
    return {
      ...base,
      code: byText.code,
      kind: byText.kind,
      severity: byText.severity,
      hint: byText.hint,
      resendable: byText.resendable,
    }
  }

  // ③ 都不中：unknown，但仍然带上了 rawCode/detail 供人工排查
  const fallback = CODE_TABLE.unknown
  return {
    ...base,
    code: 'unknown',
    kind: fallback.kind,
    severity: fallback.severity,
    hint: fallback.hint,
    resendable: fallback.resendable,
  }
}

/**
 * 同类错误合并计数。
 *
 * 同一条提示条只能显示一条错误，而连续失败（连点三次发送、限流连撞两次）会不断
 * 覆盖它：律师看到的是「又一条一模一样的红字」，判断不出「是不是一直在同一个坑里」。
 * 按 code 合并、计数累加、文案取最新——code 变了就是另一件事，从头计数。
 */
export function mergeError(prev: ClassifiedError | null, next: ClassifiedError): ClassifiedError {
  if (!prev || prev.code !== next.code) return next
  return { ...next, repeat: prev.repeat + 1 }
}

export type ErrorActionId = 'retry' | 'switch_backend' | 'compact_context'

export interface ErrorAction {
  id: ErrorActionId
  label: string
  /** 倒计时秒数（仅 `retry` 且后端给了 `retry_after` 时有值） */
  waitSeconds?: number
}

/**
 * `detail` 里的「还能等几秒」→ 秒。
 *
 * 两个键名都认：后端 `errors.py` 现在发的是 `retry_after_seconds`（从上游 429 的
 * `retry-after` 头/消息里抽出来的），而契约文档写的是 `retry_after`。只认一个
 * 的下场是按钮永远不出现，而没有任何测试会红——所以两个都读，以后端实际字段优先。
 * 字符串数字也认（header 原值可能是字符串）。
 */
function retryAfterSeconds(detail: Record<string, unknown> | undefined): number | null {
  const raw = detail?.retry_after ?? detail?.retry_after_seconds
  const n = typeof raw === 'number' ? raw : typeof raw === 'string' ? Number(raw) : NaN
  if (!Number.isFinite(n) || n < 0) return null
  // 上界只是防呆：后端若误发 86400，不该让按钮卡一整天
  return Math.min(Math.floor(n), 3600)
}

/**
 * code → 动作按钮。**没有对应动作就返回空数组**，组件据此不渲染按钮
 * （渲染一个点不动的禁用按钮，律师只会以为功能坏了）。
 *
 * 只认 code、不认文案：文案命中时（旧后端）拿不到 `retry_after` 这类参数，
 * 与其猜一个秒数，不如老实回到「建议 + 诊断 + 关闭」。
 */
export function errorActions(error: ClassifiedError): ErrorAction[] {
  switch (error.code) {
    case 'rate_limited': {
      const wait = retryAfterSeconds(error.detail)
      return [
        {
          id: 'retry',
          label: wait === null ? '稍后重试' : wait > 0 ? `等 ${wait} 秒后重试` : '重试',
          waitSeconds: wait ?? undefined,
        },
      ]
    }
    case 'capability_unsupported':
      return [{ id: 'switch_backend', label: '换个后端' }]
    case 'context_exceeded':
      return [{ id: 'compact_context', label: '压缩上下文' }]
    default:
      return []
  }
}

/** detail 的单值格式化：稳定、单行、不超长（律师要把它念给技术支持听） */
function detailValue(v: unknown): string {
  if (typeof v === 'string') return v.length > 200 ? `${v.slice(0, 200)}…` : v
  if (typeof v === 'number' || typeof v === 'boolean' || v === null) return String(v)
  try {
    const text = JSON.stringify(v)
    return text.length > 200 ? `${text.slice(0, 200)}…` : text
  } catch {
    return '[无法序列化]'
  }
}

/**
 * 诊断文本（复制给管理员）：时间 + 错误码 + 范围 + 详情 + 原文。
 *
 * 键排序是为了同一类错误在不同机器上可 diff——支持人员比对两份诊断时，字段乱序
 * 会白白多花几分钟。
 */
export function diagnosticsOf(error: ClassifiedError, now = Date.now()): string {
  const lines = [
    `时间：${new Date(now).toISOString()}`,
    `错误码：${error.code}`,
  ]
  if (error.rawCode && error.rawCode !== error.code) lines.push(`后端原始码：${error.rawCode}`)
  if (error.scope) lines.push(`范围：${error.scope}`)
  if (error.lane) lines.push(`来源：${error.lane}`)
  if (error.repeat > 1) lines.push(`连续次数：${error.repeat}`)
  if (error.detail) {
    const keys = Object.keys(error.detail).sort()
    if (keys.length > 0) {
      lines.push(`详情：${keys.map((k) => `${k}=${detailValue(error.detail![k])}`).join(' | ')}`)
    }
  }
  lines.push(`原文：${error.message}`)
  return lines.join('\n')
}
