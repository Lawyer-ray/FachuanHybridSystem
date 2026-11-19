/**
 * 转录流里的工具行（单栏 / 历史回放时按时间平铺的那条 `<details>`）。
 *
 * 从 MessageList 拆出（后者已到软红线）。多栏时工具行不在这里出现——它们归位到
 * 各自那一栏（正文未到时是气泡内的活动行 StreamActivity，到了之后是气泡下方的
 * chip ToolChips）。单栏没有「谁的工具」这个问题，按到达顺序平铺本身就是对的，
 * 所以仍保留整行可展开的形态（返回值常常要看，chip 太窄）。
 */

import { memo } from 'react'
import { Wrench } from 'lucide-react'

import { shortToolName } from '../domain'
import type { ChatMessage } from '../types'

// 必须 memo：流式每个 delta 都 set({messages: s.messages.map(…)}) 造出新数组 +
// 新消息对象，不 memo 的话整棵工具行 DOM 都要重算（200 条历史 × 几百个 delta）。
// props 只有 message 一个引用，未变的消息走浅比较 bail out。
export const ToolRow = memo(function ToolRow({ message }: { message: ChatMessage }) {
  const name = shortToolName(message.toolName)
  return (
    <details className="group rounded-[10px] border border-border bg-secondary/40 px-2.5 py-1.5">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[12px] text-muted-foreground">
        <Wrench className="h-3 w-3 flex-none" />
        <span className="truncate">
          {message.content ? '已完成' : '调用中'} · {name}
        </span>
      </summary>
      {message.content && (
        <pre className="mt-1.5 max-h-56 overflow-y-auto border-t border-border pt-1.5 font-mono text-[11px] leading-relaxed break-all whitespace-pre-wrap text-secondary-foreground">
          {message.content}
        </pre>
      )}
    </details>
  )
})
