/**
 * 挂在某一栏回答下面的工具 chip（`🔧 get_current_user · list_lawyers`）。
 *
 * 从 MessageList 拆出（后者要控在软红线内）。为什么是**一行紧凑 chip串**而不是
 * 整行 `<details>`（ToolRow）：四个 agent 各来几条就把它那栏撑成一面墙。
 *
 * 也不做成「折叠成一个总数」：律师问「你查过什么」时最想看的是**具体查了哪些**，
 * 收成「3 个工具」等于把答案藏起来。
 */

import { memo } from 'react'
import { Wrench } from 'lucide-react'

import { shortToolName } from '../domain'
import type { ChatMessage } from '../types'

import { DiffBlock } from './markdown/DiffBlock'

export const OwnToolList = memo(function OwnToolList({ tools }: { tools: ChatMessage[] }) {
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1">
      {tools.map((tool) => (
        <ToolChip key={tool.id} tool={tool} />
      ))}
    </div>
  )
})

/** 单个工具 chip：默认只显示名字，点开看返回值（``<details>`` 天然支持）。 */
export const ToolChip = memo(function ToolChip({ tool }: { tool: ChatMessage }) {
  const name = shortToolName(tool.toolName)
  const done = Boolean(tool.content)
  return (
    <details className="group/chip max-w-full rounded-[6px] border border-border/70 bg-secondary/30">
      <summary
        className="flex cursor-pointer list-none items-center gap-1 px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        title={name}
      >
        <Wrench className={`h-2.5 w-2.5 flex-none ${done ? '' : 'animate-pulse'}`} />
        <span className="max-w-[190px] truncate font-mono">{name}</span>
        <span className="flex-none text-[10px] opacity-70">{done ? '' : '…'}</span>
      </summary>
      {done && tool.rewrite && (
        <div className="max-w-[min(560px,80vw)] px-1.5 pb-1">
          <DiffBlock
            original={tool.rewrite.original}
            replacement={tool.rewrite.replacement}
            filename={tool.rewrite.filename}
          />
        </div>
      )}
      {done && (
        <pre className="max-h-40 max-w-[min(420px,70vw)] overflow-auto border-t border-border/70 px-1.5 py-1 font-mono text-[10.5px] leading-relaxed break-all whitespace-pre-wrap text-secondary-foreground">
          {tool.content}
        </pre>
      )}
    </details>
  )
})
