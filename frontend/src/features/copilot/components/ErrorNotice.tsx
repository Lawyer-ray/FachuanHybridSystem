/**
 * 错误提示条：把 `lastError` 从「一行不可操作的红字」变成「能看懂、能关掉、
 * 能拿去求助、必要时能给一个动作」的一条。
 *
 * 分层（照 goose 的四层错误呈现收口，但只做其中一层）：
 * - 会话加载失败 → 仍走原路径（整块提示 + 切会话重试）
 * - **轮次/交互失败 → 本组件**（转录下方，不覆盖已生成内容）
 * - 渲染崩溃 → 不做（需 ErrorBoundary，另议）
 *
 * ## 动作按钮只看 `code`，没有对应动作就不渲染
 *
 * 后端 `error` 事件现在带 `code`/`scope`/`detail`（经 `domain/error.ts` 的
 * `encodeError` 编进 `lastError` 这一个字符串，store 状态形状不用改）。动作由
 * `errorActions(code)` 决定：
 *
 * | code | 按钮 | 说明 |
 * |:--|:--|:--|
 * | `rate_limited` | 等 N 秒后重试 | N 来自 `detail.retry_after`；没有秒数就只写「稍后重试」 |
 * | `capability_unsupported` | 换个后端 | 只切**新对话**的后端（已有会话的 agent_kind 不可换） |
 * | `context_exceeded` | 压缩上下文 | 直接调 store 的 compactContext |
 * | 其余 | 无 | 保持「建议 + 诊断 + 关闭」 |
 *
 * **没有 handler 的动作一律不渲染**：渲染一个点不动的禁用按钮，律师会以为功能
 * 坏了，而不是「你现在没有别的后端可选」。
 *
 * ## 为什么不做「重发」
 *
 * 重发需要拿回本轮**已组装好**的出站正文（含业务锚点/引用块/页面描述），而
 * `send()` 会再注入一次锚点，直接复用会导致重复注入——同一份引用在消息里出现
 * 两遍，模型会以为律师引了两份材料。所以 `rate_limited` 的「重试」只把提示放行
 * （`clearError`），出站正文由律师自己按一次发送生成；等后端提供「按 run 重跑」
 * 语义后再做真正的重试。
 */

import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ArrowLeftRight, Check, Copy, Info, Minimize2, RefreshCw, X } from 'lucide-react'

import { useCopyFeedback } from '@/hooks/use-copy-feedback'

import type { AgentBackendOption } from '../types'
import {
  classifyError,
  diagnosticsOf,
  errorActions,
  mergeError,
  type ClassifiedError,
  type ErrorActionId,
  type ErrorInput,
} from '../domain'
import { useCopilot } from '../store'

const TONE: Record<'info' | 'warn' | 'error', string> = {
  info: 'border-border bg-secondary/40',
  warn: 'border-amber-500/40 bg-amber-500/5',
  error: 'border-destructive/40 bg-destructive/5',
}

const ICON_TONE: Record<'info' | 'warn' | 'error', string> = {
  info: 'text-muted-foreground',
  warn: 'text-amber-600 dark:text-amber-500',
  error: 'text-destructive',
}

const ACTION_ICON: Record<ErrorActionId, typeof RefreshCw> = {
  retry: RefreshCw,
  switch_backend: ArrowLeftRight,
  compact_context: Minimize2,
}

const ACTION_TITLE: Record<ErrorActionId, (target: AgentBackendOption | null) => string> = {
  retry: () => '点这里清掉提示，由你自己再发一次（系统不代为重发：复用出站正文会重复注入引用）',
  switch_backend: (target) =>
    target ? `新对话改用 ${target.label}（本对话的后端不可更换）` : '换一个后端开新对话',
  compact_context: () => '压缩本会话的历史，腾出上下文空间后再问',
}

/**
 * 分类 + 同 code 合并计数。
 *
 * 用 ref 缓存上一次结果而不是把它塞进 state：`useMemo` 在 StrictMode / 重复渲染下
 * 会重跑，靠「入参没变（code + 文案 + scope 三项全同）就直接返回缓存」保证幂等——
 * 否则一次渲染就能把连续次数刷到 2，律师看到「同类错误 ×2」而其实只报了一次。
 */
function useMergedError(source: string | ErrorInput | null | undefined): ClassifiedError | null {
  const next = useMemo(() => classifyError(source), [source])
  const [merged, setMerged] = useState<ClassifiedError | null>(null)
  // 合并放到 effect 里：渲染期读写 ref 会被 React Compiler 直接判错（"Cannot access
  // refs during render"），而这里确实需要「跨渲染累加」——那是副作用，只能在 effect。
  // 代价是计数变化会多一次渲染；它只在错误文案变化时发生，不在热路径上。
  useEffect(() => {
    setMerged((prev) => (next ? mergeError(prev, next) : null))
  }, [next])
  return merged
}

/** 限流倒计时：到点自动解锁按钮。只在本条错误内计数，换错误就重置 */
function useCountdown(seconds: number, resetKey: string): number {
  const [left, setLeft] = useState(seconds)
  useEffect(() => setLeft(seconds), [seconds, resetKey])
  useEffect(() => {
    if (left <= 0) return
    const timer = window.setTimeout(() => setLeft((v) => v - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [left])
  return Math.max(left, 0)
}

/** 可切换的目标后端：只挑**可用**且不是当前这个的（不可用项选了会在建会话后炸） */
function pickBackendTarget(backends: AgentBackendOption[], current: string): AgentBackendOption | null {
  return backends.find((b) => b.available && b.kind !== current) ?? null
}

export function ErrorNotice({ input }: {
  /**
   * 覆盖数据源（默认读 store 的 `lastError`）。
   *
   * 留这个口子是为了让**已经拿到结构化错误**的调用方（例如将来的某个面板）直接
   * 把 `{code, message, detail}` 传进来，不必先编成字符串再拆。`MessageList`
   * 目前仍是 `<ErrorNotice />`，走 store。
   */
  input?: string | ErrorInput | null
} = {}) {
  const lastError = useCopilot((s) => s.lastError)
  const clearError = useCopilot((s) => s.clearError)
  const compactContext = useCopilot((s) => s.compactContext)
  const backends = useCopilot((s) => s.backends)
  const selectedAgentKind = useCopilot((s) => s.selectedAgentKind)
  const selectAgentKind = useCopilot((s) => s.selectAgentKind)
  const { copied, copy } = useCopyFeedback({ resetMs: 1500 })

  const source = input ?? lastError
  const error = useMergedError(source)
  const actions = useMemo(() => (error ? errorActions(error) : []), [error])
  const retryAction = actions.find((a) => a.id === 'retry')
  const remaining = useCountdown(retryAction?.waitSeconds ?? 0, error ? `${error.code}|${error.message}` : '')

  if (!error || !source) return null

  // 出错的后端（`scope` 里若写的是某个后端 kind 就以它为准，否则用当前选择）
  const currentKind = backends.find((b) => b.kind === error.scope)?.kind ?? selectedAgentKind
  const switchTarget = pickBackendTarget(backends, currentKind)

  // handler 为 null = 这个动作现在做不到（例如没有别的可用后端）→ 不渲染按钮
  const handlers: Record<ErrorActionId, (() => void) | null> = {
    // 不代为重发，只放行提示：理由见文件头「为什么不做重发」
    retry: clearError,
    compact_context: () => void compactContext(),
    switch_backend: switchTarget
      ? () => {
          selectAgentKind(switchTarget.kind)
          clearError()
        }
      : null,
  }
  const visible = actions.filter((a) => handlers[a.id])

  const Icon = error.severity === 'info' ? Info : AlertTriangle
  const counting = retryAction?.waitSeconds !== undefined && retryAction.waitSeconds > 0 && remaining > 0

  return (
    <div
      className={`mt-2 flex items-start gap-2 rounded-[9px] border px-2.5 py-2 ${TONE[error.severity]}`}
      // error 用 alert（读屏立即打断）；warn/info 用 status（不抢当前朗读）
      role={error.severity === 'error' ? 'alert' : 'status'}
      data-testid="error-notice"
      data-code={error.code}
      data-kind={error.kind}
      data-scope={error.scope}
    >
      <Icon className={`mt-0.5 h-3.5 w-3.5 flex-none ${ICON_TONE[error.severity]}`} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[12.5px] font-medium leading-relaxed">{error.message}</span>
          {error.lane && (
            <span className="rounded-[4px] bg-secondary px-1 py-px text-[10.5px] text-muted-foreground">
              {error.lane}
            </span>
          )}
          {error.resendable && (
            <span className="rounded-[4px] border border-border px-1 py-px text-[10.5px] text-muted-foreground">
              可原样重发
            </span>
          )}
          {error.repeat > 1 && (
            <span
              className="rounded-[4px] border border-border px-1 py-px text-[10.5px] text-muted-foreground"
              title="同一个错误码连续出现（不是新问题，别反复重发）"
            >
              同类错误 ×{error.repeat}
            </span>
          )}
        </div>
        <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{error.hint}</p>
      </div>
      <div className="flex flex-none items-center gap-0.5">
        {visible.map((action) => {
          const ActionIcon = ACTION_ICON[action.id]
          // `visible` 已滤过一遍 handlers；这里再取一次就要自己兜住「取不到」——
          // 用下标断言会让两次判定脱钩（漏一个 `!` 就是运行期 undefined 当 onClick）
          const handler = handlers[action.id]
          if (!handler) return null
          // 倒计时期间显示剩余秒数（律师要看到「还要等多久」），到点变回「重试」
          const labelled = action.id === 'retry' && action.waitSeconds !== undefined && action.waitSeconds > 0
          const label = labelled ? (counting ? `等 ${remaining} 秒后重试` : '重试') : action.label
          return (
            <button
              key={action.id}
              type="button"
              disabled={action.id === 'retry' && counting}
              className="flex h-6 items-center gap-1 rounded-[5px] border border-border px-1.5 text-[11px] text-foreground transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
              title={ACTION_TITLE[action.id](switchTarget)}
              onClick={handler}
            >
              <ActionIcon className="size-3" aria-hidden />
              {label}
            </button>
          )
        })}
        <button
          type="button"
          className="flex h-6 items-center gap-1 rounded-[5px] px-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          title="复制时间、错误码、后端与详情（发给管理员排查）"
          onClick={() => void copy(diagnosticsOf(error))}
        >
          {copied ? <Check className="size-3" aria-hidden /> : <Copy className="size-3" aria-hidden />}
          {copied ? '已复制' : '诊断'}
        </button>
        <button
          type="button"
          className="flex h-6 w-6 items-center justify-center rounded-[5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          aria-label="关闭这条提示"
          title="关闭"
          onClick={clearError}
        >
          <X className="size-3" aria-hidden />
        </button>
      </div>
    </div>
  )
}
