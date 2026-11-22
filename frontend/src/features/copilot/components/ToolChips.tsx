/**
 * 工具 chip：收起时是一枚小 chip（一行放多枚、自动换行），点开后独占一整行看返回值。
 *
 * 两个入口，都是「一串 chip」：
 * - 单栏转录流：{@link ToolChipList} 把**连续的** tool 消息收成一条 chip 带
 *   （AnswerGroupView 调）。这是「16 条工具吃掉约 450px」的正解——每条的实际信息
 *   只有工具名 + 耗时，给它一整行是浪费；
 * - 多栏的每一栏：{@link OwnToolList} 挂在气泡下方（Bubble 调），四个 agent 各来
 *   几条也不会把那栏撑成一面墙。
 *
 * 也不做成「折叠成一个总数」：律师问「你查过什么」时最想看的是**具体查了哪些**，
 * 收成「3 个工具」等于把答案藏起来。
 *
 * ## 为什么 chip 里还留着 `<details>`
 *
 * 当年单栏用整行 {@link ToolRow} 的**唯一**理由是「返回值常常要看，chip 太窄」。
 * 现在这条由排版解决：收起时 chip 只占几个字，点开的那一枚 `open:basis-full`
 * 在换行容器里独占一行，返回值拿整行宽度（旧的 `max-w-[min(420px,70vw)]` 窄上限已删）。
 *
 * ## 五态措辞与无障碍
 *
 * - **五个状态全部只出图标**：`ok` 绿勾 / `error` 红叉 / `stopped` 灰横线 / `running`
 *   转圈 / `preparing` 灰点。可见文字为零（用户：「用打勾或者打叉来表示结果，我会自己
 *   点开」）；「已完成」在 16 条工具里重复 16 遍本来就是纯噪声；
 * - 字**没有删**，只是移进 `sr-only`（见 `ToolStateWord`）：眼睛看不到、耳朵听得到；
 * - `list-style: none` 去掉了 summary 的原生三角，所以补一枚可见 chevron（`open` 时转 90°），
 *   否则没人知道这枚 chip 还能点；
 * - summary 里只有图标与文本，不嵌 button/link（交互元素嵌进 summary 会变成两个焦点）。
 */

import { memo } from 'react'
import { ChevronRight } from 'lucide-react'

import { formatToolContent, shortToolName, toolStateLabel, toolStateOf, toolSummary } from '../domain'
import type { ChatMessage } from '../types'

import { DiffBlock } from './markdown/DiffBlock'
import { ToolElapsed, ToolStateIcon, ToolStateWord } from './ToolRow'

/**
 * chip 带布局：一行放不下就换行，`flex-wrap: balance` 让最后一行不至于只剩一枚孤字。
 *
 * `supports-` 守卫不是装饰，是**必须的**：`flex-wrap: balance` 在 Firefox/Safari 还没有，
 * 裸写 `[flex-wrap:balance]` 在那边是无效取值，整条带子会退回初始值 `nowrap`（挤成
 * 一行溢出）；守卫以后不支持就落到前一个 `flex-wrap: wrap`，支持才叠加 `balance`。
 */
const CHIP_WRAP = 'flex flex-wrap supports-[flex-wrap:balance]:[flex-wrap:balance] items-center gap-1'

/** 一串 chip（单栏转录流与多栏气泡下共用，差别只有外边距）。 */
export const ToolChipList = memo(function ToolChipList({
  tools,
  className,
}: {
  tools: ChatMessage[]
  className?: string
}) {
  return (
    <div className={className ? `${CHIP_WRAP} ${className}` : CHIP_WRAP}>
      {tools.map((tool) => (
        <ToolChip key={tool.id} tool={tool} />
      ))}
    </div>
  )
})

/** 多栏里某个 agent 自己查过的工具：挂在它自己的话下面，与正文留一点空。 */
export const OwnToolList = memo(function OwnToolList({ tools }: { tools: ChatMessage[] }) {
  return <ToolChipList tools={tools} className="mt-1.5" />
})

/** 单枚工具 chip：收起时只有状态与短名，点开独占整行看返回值（`<details>` 天然支持）。 */
export const ToolChip = memo(function ToolChip({ tool }: { tool: ChatMessage }) {
  const state = toolStateOf(tool)
  const label = toolStateLabel(state)
  const name = shortToolName(tool.toolName)
  const settled = state === 'ok' || state === 'error'
  // 原文归一化（拆 MCP 信封 / 解转义 / JSON 美化 / HTML 兜底，见 domain/tool-content）
  const content = formatToolContent(tool.content)
  return (
    <details className="group/chip max-w-full rounded-[6px] border border-border/70 bg-secondary/30 open:basis-full">
      <summary
        className="flex cursor-pointer list-none items-center gap-1 px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        title={`${label.text} · ${toolSummary(tool)}`}
      >
        <ToolStateIcon state={state} className="h-2.5 w-2.5" />
        <span className="max-w-[190px] truncate font-mono">{name}</span>
        {/* 状态只出图标，字给读屏 */}
        <ToolStateWord state={state} />
        <ToolElapsed message={tool} />
        {state === 'running' && tool.toolStartedAt === undefined && (
          <span className="flex-none text-[10px] opacity-70">…</span>
        )}
        <ChevronRight
          className="h-2.5 w-2.5 flex-none opacity-60 transition-transform group-open/chip:rotate-90"
          aria-hidden="true"
        />
      </summary>
      {settled && tool.rewrite && (
        <div className="px-1.5 pb-1">
          <DiffBlock
            original={tool.rewrite.original}
            replacement={tool.rewrite.replacement}
            filename={tool.rewrite.filename}
          />
        </div>
      )}
      {content && (
        <pre className="max-h-40 overflow-auto border-t border-border/70 px-1.5 py-1 font-mono text-[10.5px] leading-relaxed break-all whitespace-pre-wrap text-secondary-foreground">
          {content}
        </pre>
      )}
    </details>
  )
})
