/**
 * 工具行的展示口径（纯函数，无 React、无 IO）。
 *
 * 律师看工具行只问两件事：「它在干什么」「跑完了没有、跑了多久」。原先只有
 * 「调用中 / 结果」两态，`tool_call` 与 `tool_result` 都没记时间：跑多久、成没成
 * 都答不上来。这里把名称归族、给状态一句人话 + 色调、给耗时格式，渲染层
 * （ToolRow / ToolChips）只负责排版。
 */

import type { ChatMessage } from '../types'
import { shortToolName } from './reference'

/** 工具族：只用于选动作词与标题，不参与权限/执行判断 */
export type ToolKind = 'read' | 'search' | 'write' | 'execute' | 'fetch' | 'other'

/**
 * 工具运行态（`ChatMessage` 的四个可选字段）。
 *
 * 为什么定义在这里而不是 `types.ts`：`types.ts` 已撞 450 行红线，而这四个字段的
 * 语义（五态、耗时口径、入参只用于标题）全部由本模块解释——放这里与口径同源。
 * `ChatMessage extends ToolRunState`，消费方仍然按 ChatMessage 用。
 */
export interface ToolRunState {
  /** 五态：preparing 已声明未执行 / running / ok / error / stopped。**不能靠 content 有无推断**。 */
  toolState?: 'preparing' | 'running' | 'ok' | 'error' | 'stopped'
  /** 开始/结束时刻（ms）。缺 startedAt 就不显示耗时——宁可空着，也不编一个 0.0s。 */
  toolStartedAt?: number
  toolEndedAt?: number
  /** 工具入参（只用于「读取 X」这类短标题，不要整份塞进 DOM 文本）。 */
  toolArgs?: unknown
}

/** 执行态（旧数据缺省时见 {@link toolStateOf}） */
export type ToolState = NonNullable<ToolRunState['toolState']>

export type ToolTone = 'muted' | 'ok' | 'warn' | 'error'

/** 名称族 → 关键词：按**包含**匹配，不枚举工具名（工具会增删，族不会）。
 *  顺序即优先级：`web_search` 归 search 而不是 fetch。 */
const KIND_WORDS: Array<[ToolKind, readonly string[]]> = [
  ['search', ['search', 'find', 'grep', 'glob', 'query']],
  ['read', ['read', 'get_', 'list_', 'show_']],
  ['write', ['write', 'edit', 'create', 'update', 'delete', 'rewrite', 'move']],
  ['execute', ['bash', 'shell', 'exec', 'run', 'python', 'node']],
  ['fetch', ['fetch', 'http', 'web', 'url', 'download']],
]

export function toolKind(name: string): ToolKind {
  const short = shortToolName(name).toLowerCase()
  for (const [kind, words] of KIND_WORDS) {
    if (words.some((word) => short.includes(word))) return kind
  }
  return 'other'
}

/** 各族标题的动词与「读哪个入参字段」：只读这些已知键，取不到就只回工具短名 */
const KIND_SPEC: Record<ToolKind, { verb: string; keys: readonly string[] }> = {
  read: { verb: '读取', keys: ['path', 'file', 'filename', 'file_path', 'name', 'title'] },
  search: { verb: '检索', keys: ['query', 'q', 'keyword', 'pattern', 'text', 'name'] },
  write: { verb: '写入', keys: ['path', 'file', 'filename', 'file_path', 'name', 'title'] },
  execute: { verb: '执行', keys: ['command', 'cmd', 'script', 'language'] },
  fetch: { verb: '获取', keys: ['url', 'query', 'q', 'keyword'] },
  other: { verb: '', keys: [] },
}

const PATH_KEYS = new Set(['path', 'file', 'filename', 'file_path'])
const SUMMARY_MAX = 40

function argHint(args: unknown, kind: ToolKind): string {
  if (typeof args !== 'object' || args === null) return ''
  const record = args as Record<string, unknown>
  for (const key of KIND_SPEC[kind].keys) {
    const value = record[key]
    if (typeof value !== 'string' && typeof value !== 'number') continue
    let text = String(value).trim()
    if (kind === 'execute' && (key === 'command' || key === 'cmd' || key === 'script')) {
      // 命令只取第一个词（解释器 / 可执行文件），后面是参数噪声
      text = text.split(/\s+/)[0] ?? ''
    }
    if (PATH_KEYS.has(key)) text = text.split(/[\\/]/).pop() ?? text
    if (text) return text
  }
  return ''
}

const clampSummary = (text: string): string =>
  text.length > SUMMARY_MAX ? `${text.slice(0, SUMMARY_MAX - 1)}…` : text

/** 「正在做什么」一句短标题（≤40 字）；只读已知字段，取不到就只回工具短名 */
export function toolSummary(message: Pick<ChatMessage, 'toolName' | 'toolArgs'>): string {
  const name = shortToolName(message.toolName)
  const kind = toolKind(name)
  const hint = argHint(message.toolArgs, kind)
  return hint && kind !== 'other' ? clampSummary(`${KIND_SPEC[kind].verb} ${hint}`) : clampSummary(name)
}

/** 工具耗时：`0.4s` / `12s` / `1m05s`。未结束用 now；没有开始时刻返回空串（不编造） */
export function formatElapsed(startedAt?: number, endedAt?: number, now = Date.now()): string {
  if (startedAt === undefined || !Number.isFinite(startedAt)) return ''
  const end = endedAt ?? now
  if (!Number.isFinite(end)) return ''
  const ms = Math.max(0, end - startedAt)
  if (ms < 1000) return `${(Math.floor(ms / 100) / 10).toFixed(1)}s`
  const total = Math.round(ms / 1000)
  if (total < 60) return `${total}s`
  return `${Math.floor(total / 60)}m${String(total % 60).padStart(2, '0')}s`
}

/** 旧数据（无 toolState）按结果有无回落：有内容=成功，空=还在跑 */
export function toolStateOf(message: Pick<ChatMessage, 'toolState' | 'content'>): ToolState {
  return message.toolState ?? (message.content ? 'ok' : 'running')
}

export function toolStateLabel(state: ToolState): { text: string; tone: ToolTone } {
  switch (state) {
    case 'preparing':
      return { text: '准备中', tone: 'muted' }
    case 'running':
      return { text: '调用中', tone: 'muted' }
    case 'ok':
      return { text: '已完成', tone: 'ok' }
    case 'error':
      return { text: '失败', tone: 'error' }
    case 'stopped':
      return { text: '已中止', tone: 'warn' }
  }
}
