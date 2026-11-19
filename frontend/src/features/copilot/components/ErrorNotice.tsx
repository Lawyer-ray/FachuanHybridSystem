/**
 * 错误提示条：把 `lastError` 从「一行不可操作的红字」变成「能看懂、能关掉、
 * 能拿去求助」的一条。
 *
 * 分层（照 goose 的四层错误呈现收口，但只做其中一层）：
 * - 会话加载失败 → 仍走原路径（整块提示 + 切会话重试）
 * - **轮次/交互失败 → 本组件**（转录下方，不覆盖已生成内容）
 * - 渲染崩溃 → 不做（需 ErrorBoundary，另议）
 *
 * 为什么不做「重试」按钮：重发需要拿回本轮**已组装好**的出站正文（含业务锚点/
 * 引用块），而 `send()` 会再注入一次锚点，直接复用会导致重复注入；留到后端
 * 提供「按 run 重跑」语义后再做。这里只给「能不能原样再发一次」的明确指引 +
 * 可复制的诊断信息。
 */

import { useMemo } from 'react'
import { AlertTriangle, Check, Copy, Info, X } from 'lucide-react'

import { useCopyFeedback } from '@/hooks/use-copy-feedback'

import { classifyError, diagnosticsOf, splitLanePrefix } from '../domain'
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

export function ErrorNotice() {
  const lastError = useCopilot((s) => s.lastError)
  const clearError = useCopilot((s) => s.clearError)
  const { copied, copy } = useCopyFeedback({ resetMs: 1500 })
  const error = useMemo(() => classifyError(lastError), [lastError])

  if (!error || !lastError) return null

  const lane = splitLanePrefix(lastError).lane
  const Icon = error.severity === 'info' ? Info : AlertTriangle

  return (
    <div
      className={`mt-2 flex items-start gap-2 rounded-[9px] border px-2.5 py-2 ${TONE[error.severity]}`}
      role="status"
      data-testid="error-notice"
      data-code={error.code}
    >
      <Icon className={`mt-0.5 h-3.5 w-3.5 flex-none ${ICON_TONE[error.severity]}`} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[12.5px] font-medium leading-relaxed">{error.message}</span>
          {lane && (
            <span className="rounded-[4px] bg-secondary px-1 py-px text-[10.5px] text-muted-foreground">
              {lane}
            </span>
          )}
          {error.resendable && (
            <span className="rounded-[4px] border border-border px-1 py-px text-[10.5px] text-muted-foreground">
              可原样重发
            </span>
          )}
        </div>
        <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{error.hint}</p>
      </div>
      <div className="flex flex-none items-center gap-0.5">
        <button
          type="button"
          className="flex h-6 items-center gap-1 rounded-[5px] px-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          title="复制时间、错误码与原文（发给管理员排查）"
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
