/**
 * 后端错误码 → 前端呈现档位（code-first 的唯一一张表）。
 *
 * 从 `error.ts` 拆出：那边原本一张文案表 + 分类 + 诊断 + 动作都在一起，加完 code
 * 契约直接顶到 500 行(>450 硬红线)。拆点选在「**后端说什么**」和「**前端怎么呈现**」
 * 之间：本文件只认后端 code（以及后端历史拼写的别名），不碰文案、不碰 store、不碰
 * React；`error.ts` 负责把三分支（code / 旧文案 / unknown）拼成一条可展示的错误。
 *
 * 迁移线索：第一版（4f248db9）只按中文文案 `includes` 归类，因为那时后端 `error`
 * 事件只有 `message`。文案表的正确性依赖后端文案一字不改，改一个字就静默落到
 * unknown，而且没有任何测试会红——两份表从来不在同一份代码里。后端补上
 * `code`/`scope`/`detail` 之后，分类以 code 为准，文案表退化成旧后端的兜底。
 */

/**
 * 后端 `error` 事件的错误码（与后端 agent 契约同名，一个都不能改拼写）。
 *
 * `unknown` 是**本地**兜底值：后端发的任何认不出来的 code 都折成它。
 */
export type ErrorCode =
  | 'rate_limited'
  | 'quota_exhausted'
  | 'backend_unavailable'
  | 'capability_unsupported'
  | 'context_exceeded'
  | 'upstream_timeout'
  | 'tool_args_invalid'
  | 'session_not_found'
  | 'auth_failed'
  | 'too_many_agents'
  | 'unknown'

/**
 * UI 大类：只决定分色/图标/文案分档，**不决定动作按钮**。
 *
 * 与 {@link ErrorCode} 正交：同一个 code 可能落到不同 kind（后端把 5xx 报成
 * `backend_unavailable`，前端按「网络/网关」呈现），而旧后端的文案命中时 code 可能
 * 是 `unknown` 但 kind 仍然精确。动作只看 code（见 `errorActions`）。
 */
export type ErrorKind =
  | 'network'
  | 'stream_broken'
  | 'rate_limited'
  | 'quota'
  | 'turn_ended'
  | 'capability'
  | 'attachment'
  | 'compact'
  | 'task'
  | 'history'
  | 'tool'
  | 'unknown'

export type ErrorSeverity = 'info' | 'warn' | 'error'

export interface CodeProfile {
  kind: ErrorKind
  severity: ErrorSeverity
  hint: string
  resendable: boolean
}

/**
 * code → 呈现档位。改这里就是改「用户看到什么」，不需要碰任何组件。
 *
 * `resendable` 的判定标准是「原样再发一次是否**可能**成功」：限流、超时、后端没起来
 * 都可能；配额用尽、能力不支持、上下文超限则**必然**再撞一次同样的墙，标成可重发
 * 只会让用户白等一轮。
 */
export const CODE_TABLE: Record<ErrorCode, CodeProfile> = {
  rate_limited: {
    kind: 'rate_limited',
    severity: 'warn',
    hint: '这是排队限流，不是你的问题。等提示里的秒数过去，把刚才那句原样再发一次即可。',
    resendable: true,
  },
  quota_exhausted: {
    kind: 'quota',
    severity: 'error',
    // 不说「必须充值」：后端把「并发席位满 / 执行位满」也归到这个 code
    // （errors.py 的 BUSY → quota_exhausted），那种情况等一会儿就恢复
    hint: '本账号或这个模型的额度（或并发席位）已经用尽，重发不会立刻恢复。稍后重试，或联系管理员加额度。',
    resendable: false,
  },
  backend_unavailable: {
    kind: 'network',
    severity: 'error',
    hint: '后端没起来或网关不通。先按原样再发一次；仍失败就把「诊断」内容发给管理员。',
    resendable: true,
  },
  capability_unsupported: {
    kind: 'capability',
    severity: 'warn',
    hint: '这个后端不支持这项能力，让它再试一次也是同样结果。换一个后端（新开对话）再问。',
    resendable: false,
  },
  context_exceeded: {
    kind: 'compact',
    severity: 'warn',
    hint: '上下文超出了模型窗口，重发只会再撞一次。先压缩上下文或新开会话，再问这一句。',
    resendable: false,
  },
  upstream_timeout: {
    kind: 'stream_broken',
    severity: 'warn',
    hint: '上游等超时了，回答可能不完整。可以重发，或在会话里追问「继续说」。',
    resendable: true,
  },
  tool_args_invalid: {
    kind: 'tool',
    severity: 'error',
    hint: '模型给工具的参数不合法，这轮工具调用被后端拒了。原样重发大概率同样报错，把「诊断」发给管理员。',
    resendable: false,
  },
  session_not_found: {
    kind: 'history',
    severity: 'error',
    // 不写「请重试」：会话都不存在了，原样再发只会再撞一次同样 404。
    // 也不写「请联系管理员」：这是律师自己能处理的事（重开一个对话）。
    hint: '这个会话在服务端已不存在（被删除、或换了环境/账号）。点「新开会话」重新问一次即可——原来的上下文不会跟过去，需要的话把它一并带上。',
    resendable: false,
  },
  auth_failed: {
    kind: 'network',
    severity: 'error',
    // 后端 docstring：重试无用 → 必须重新登录或找管理员换凭证
    hint: '身份凭证失效或未配置（后端签不出访问凭证、或上游返回 401/403）。重发一百次也一样——重新登录，仍不行就把「诊断」发给管理员。',
    resendable: false,
  },
  too_many_agents: {
    kind: 'capability',
    severity: 'warn',
    hint: '一次同时问的栏数超过后端上限。先取消勾选一栏再发，不必新开会话。',
    resendable: false,
  },
  unknown: {
    kind: 'unknown',
    severity: 'error',
    // 未知错误不给空话建议：只说能做什么（复制诊断去反馈）
    hint: '把「复制诊断」的内容发给管理员，能更快定位（含本机时间、后端与错误原文）。',
    resendable: false,
  },
}

/**
 * 后端 `BackendErrorKind`（apps/agent/backends/base.py）的历史拼写 → 本文件 code。
 *
 * 只收两个**语义完全相同**的：`context_overflow` 就是上下文超限，`unavailable`
 * 就是后端没起来。`busy` / `auth` 故意不收——排队满和凭据失效没有一一对应的 code，
 * 硬套一个（比如把 `auth` 折成 `backend_unavailable`）会推出「再发一次」的建议，
 * 而真相是「再发一百次也没用，要去重新登录」。没有对应关系就老实落 unknown。
 */
const CODE_ALIAS: Record<string, ErrorCode> = {
  context_overflow: 'context_exceeded',
  unavailable: 'backend_unavailable',
  // 后端 `QuotaExceededError` 的 code 是 `quota_exceeded`（errors.py），而本表
  // 建表时写成了 `quota_exhausted`。两个都不能改（一个在后端契约里、一个已是
  // 本表现有值），用别名接上——否则「执行位满 / 排队超时」这类最需要建议的错误
  // 会落 unknown，律师看到的是一张什么都点不了的红卡。
  quota_exceeded: 'quota_exhausted',
}

/**
 * 归一化 code：别名 → 表内 → 表外一律 unknown（不抛）。
 *
 * `rawCode` 必须原样带出去：前端把没见过的 code 折成 unknown 之后，支持人员还得
 * 知道后端到底发了什么，否则「未知错误」永远查不下去。
 */
export function normalizeErrorCode(raw: string | undefined): { code: ErrorCode; rawCode: string } {
  const key = (raw ?? '').trim().toLowerCase()
  if (!key) return { code: 'unknown', rawCode: '' }
  const alias = CODE_ALIAS[key]
  if (alias) return { code: alias, rawCode: key }
  if (Object.prototype.hasOwnProperty.call(CODE_TABLE, key)) return { code: key as ErrorCode, rawCode: key }
  return { code: 'unknown', rawCode: key }
}
