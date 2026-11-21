/**
 * 转录流里的工具行（单栏 / 历史回放时按时间平铺的那条 `<details>`）。
 *
 * 从 MessageList 拆出（后者已到软红线）。多栏时工具行不在这里出现——它们归位到
 * 各自那一栏（正文未到时是气泡内的活动行 StreamActivity，到了之后是气泡下方的
 * chip ToolChips）。单栏没有「谁的工具」这个问题，按到达顺序平铺本身就是对的，
 * 所以仍保留整行可展开的形态（返回值常常要看，chip 太窄）。
 *
 * ## 五态与耗时（{@link ToolStateIcon} / {@link ToolElapsed}）
 *
 * 原先只有「调用中 / 已完成」两态，而且是从「有没有 content」推出来的：删除类工具
 * 的合法结果就是空串，于是它永远停在「调用中」；跑多久、成没成也都答不上来。
 * 现在状态由事件给（`tool_call` = running，`tool_result.is_error` = error/ok），
 * 时刻由调用方在事件到达时打点（本模块不读时钟，纯展示 + 一个本地 tick）。
 *
 * 这两个小组件也被 {@link ToolChips} 复用：chip 与整行对同一份状态必须说同一句话。
 */

import { memo, useEffect, useState } from 'react'
import { AlertTriangle, Check, Circle, Loader2, Minus } from 'lucide-react'

import { formatElapsed, shortToolName, toolStateLabel, toolStateOf, toolSummary, type ToolState } from '../domain'
import type { ChatMessage } from '../types'

import { DiffBlock } from './markdown/DiffBlock'

/** 状态色调 → 文本色（只影响「已完成/失败」这半句，不影响工具名）。 */
const TONE_TEXT = {
  muted: 'text-muted-foreground',
  ok: 'text-emerald-600 dark:text-emerald-500',
  warn: 'text-amber-600 dark:text-amber-500',
  error: 'text-destructive',
} as const

/** 五态图标：preparing 灰点 / running 转圈 / ok 对勾 / error 警示 / stopped 灰横线。 */
export const ToolStateIcon = memo(function ToolStateIcon({
  state,
  className = 'h-3 w-3',
}: {
  state: ToolState
  className?: string
}) {
  const cls = `${className} flex-none`
  if (state === 'preparing') {
    return <Circle className={`${cls} fill-muted-foreground/40 text-muted-foreground/40`} aria-hidden="true" />
  }
  if (state === 'running') return <Loader2 className={`${cls} animate-spin`} aria-hidden="true" />
  if (state === 'ok') return <Check className={`${cls} text-emerald-600 dark:text-emerald-500`} aria-hidden="true" />
  if (state === 'error') return <AlertTriangle className={`${cls} text-destructive`} aria-hidden="true" />
  return <Minus className={`${cls} text-muted-foreground`} aria-hidden="true" />
})

/**
 * 工具耗时（右侧小字）。运行中每秒刷新一次本地 tick；卸载即清 interval。
 *
 * 没有 `toolStartedAt`（历史数据）时**不显示**——宁可空着，也不编一个 `0.0s`：
 * 律师拿这个数字判断「是不是卡死」，编出来的 0 比没有更有害。
 */
export const ToolElapsed = memo(function ToolElapsed({ message }: { message: ChatMessage }) {
  const running = toolStateOf(message) === 'running' && message.toolStartedAt !== undefined
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => setTick((n) => n + 1), 1000)
    return () => window.clearInterval(timer)
  }, [running])
  const text = formatElapsed(message.toolStartedAt, message.toolEndedAt)
  if (!text) return null
  return <span className="flex-none text-[10.5px] tabular-nums opacity-70">{text}</span>
})

// 必须 memo：流式每个 delta 都 set({messages: s.messages.map(…)}) 造出新数组 +
// 新消息对象，不 memo 的话整棵工具行 DOM 都要重算（200 条历史 × 几百个 delta）。
// props 只有 message 一个引用，未变的消息走浅比较 bail out。
export const ToolRow = memo(function ToolRow({ message }: { message: ChatMessage }) {
  const state = toolStateOf(message)
  const label = toolStateLabel(state)
  const name = shortToolName(message.toolName)
  // 改写类工具：把「改了哪一句」直接画出来，而不是让律师去看 2000 字的 JSON 结果。
  // 只有结算后才画（运行中参数还在渐进完整，画出来会是个半截 diff）。
  const settled = state === 'ok' || state === 'error'
  const rewrite = settled ? message.rewrite : undefined
  return (
    <details className="group rounded-[10px] border border-border bg-secondary/40 px-2.5 py-1.5">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[12px] text-muted-foreground">
        <ToolStateIcon state={state} />
        <span className="truncate" title={toolSummary(message)}>
          {rewrite ? (
            rewrite.filename
          ) : (
            <>
              <span className={TONE_TEXT[label.tone]}>{label.text}</span> · {name}
            </>
          )}
        </span>
        <ToolElapsed message={message} />
      </summary>
      {rewrite && <DiffBlock original={rewrite.original} replacement={rewrite.replacement} filename={rewrite.filename} />}
      {message.content && (
        <details className="mt-1.5 border-t border-border pt-1.5">
          <summary className="cursor-pointer list-none text-[11px] text-muted-foreground hover:text-foreground">
            工具返回原文
          </summary>
          <pre className="mt-1 max-h-56 overflow-y-auto font-mono text-[11px] leading-relaxed break-all whitespace-pre-wrap text-secondary-foreground">
            {message.content}
          </pre>
        </details>
      )}
    </details>
  )
})
