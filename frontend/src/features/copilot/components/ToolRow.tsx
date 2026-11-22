/**
 * 整行形态的工具行：一条 `<details>` 占满一行，展开看返回值。
 *
 * **现在只是兜底形态**：单栏转录流把连续的 tool 消息收成 chip 带（见 ToolChips 的
 * `ToolChipList`），多栏时工具归位到各自那栏（正文未到时是气泡内的活动行
 * StreamActivity，到了之后是气泡下方的 chip `OwnToolList`）。会走到这里的只剩
 * 「多栏轮次里没归位到任何一栏的工具」（例如 agentKind 不属于本轮任何一栏）：它们
 * 不属于任何 agent，只能按到达顺序平铺，孤零零几条用整行最省事。
 *
 * 从 MessageList 拆出（后者已到软红线）。
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
import { Check, Circle, Loader2, Minus, X } from 'lucide-react'

import { formatElapsed, formatToolContent, shortToolName, toolStateLabel, toolStateOf, toolSummary, type ToolState } from '../domain'
import type { ChatMessage } from '../types'

import { DiffBlock } from './markdown/DiffBlock'

/**
 * 状态词（「已完成 / 失败 / 调用中」…），**只给读屏**（`sr-only`）。
 *
 * 状态一律只出图标（用户要的是「打勾或打叉，我自己点开看」）：五个状态在屏幕上都是
 * 一枚图标，字只留在无障碍树里——不许为了省像素把读屏信息删掉。chip（ToolChips）
 * 与整行（ToolRow）共用这一份措辞，同一份状态在两种形态里说同一句话。
 */
export const ToolStateWord = memo(function ToolStateWord({ state }: { state: ToolState }) {
  return <span className="sr-only">{toolStateLabel(state).text}</span>
})

/** 五态图标：preparing 灰点 / running 转圈 / ok 绿勾 / error 红叉 / stopped 灰横线。 */
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
  if (state === 'error') return <X className={`${cls} text-destructive`} aria-hidden="true" />
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
  const name = shortToolName(message.toolName)
  // 改写类工具：把「改了哪一句」直接画出来，而不是让律师去看 2000 字的 JSON 结果。
  // 只有结算后才画（运行中参数还在渐进完整，画出来会是个半截 diff）。
  const settled = state === 'ok' || state === 'error'
  const rewrite = settled ? message.rewrite : undefined
  // 原文归一化（拆 MCP 信封 / 解转义 / JSON 美化 / HTML 兜底，见 domain/tool-content）
  const content = formatToolContent(message.content)
  return (
    <details className="group rounded-[10px] border border-border bg-secondary/40 px-2.5 py-1.5">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[12px] text-muted-foreground">
        <ToolStateIcon state={state} />
        <span className="truncate" title={toolSummary(message)}>
          {rewrite ? rewrite.filename : name}
          <ToolStateWord state={state} />
        </span>
        <ToolElapsed message={message} />
      </summary>
      {rewrite && <DiffBlock original={rewrite.original} replacement={rewrite.replacement} filename={rewrite.filename} />}
      {/* 展开就直接看到原文：不再套一层「工具返回原文」的二次点击 */}
      {content && (
        <pre className="mt-1.5 max-h-56 overflow-y-auto border-t border-border pt-1.5 font-mono text-[11px] leading-relaxed break-all whitespace-pre-wrap text-secondary-foreground">
          {content}
        </pre>
      )}
    </details>
  )
})
