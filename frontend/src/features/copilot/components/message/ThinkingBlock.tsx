/**
 * 思考块（`<details>` 折叠）：assistant 气泡正文之前的那一段。
 *
 * 从 `MessageList.tsx` 按职责拆出（后者已到软红线），行为逐字不变。
 *
 * 自动收起的来龙去脉见下方 `userToggled` 的注释：`<details open>` 是静态属性、
 * 只在挂载时生效，所以必须改成受控才能「思考结束后收起」。
 */

import { memo, useEffect, useState } from 'react'
import { Brain } from 'lucide-react'

import type { ChatMessage } from '../../types'

export const ThinkingBlock = memo(function ThinkingBlock({ message }: { message: ChatMessage }) {
  const thinking = message.thinking ?? ''
  const thinkingNow = !message.thinkingDone
  // 思考结束自动收起：<details open> 是**静态属性**，只在挂载时生效——
  // 思考中以 open=true 挂载后，prop 变 false 也不会收起，于是正文开始后
  // 那片 396 字的思考内容继续占着 max-h-56，读起来就是一大块空白。
  // 改为受控：用 state 跟踪「用户是否手动改过」，没改过就跟随思考状态。
  const [userToggled, setUserToggled] = useState<boolean | null>(null)
  const open = userToggled ?? thinkingNow
  useEffect(() => {
    // 思考结束的那一刻清掉手动状态，回落到自动收起
    if (message.thinkingDone) setUserToggled((v) => (v === null ? v : null))
  }, [message.thinkingDone])
  if (!thinking) return null
  return (
    <details
      open={open}
      onToggle={(e) => setUserToggled(e.currentTarget.open)}
      className="mb-1.5 rounded-[10px] border border-dashed border-border bg-secondary/30 px-2.5 py-1.5"
    >
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[12px] text-muted-foreground">
        <Brain className="h-3 w-3 flex-none" />
        {/* 思考中用渐变流光（copilot-shimmer），结束后回落普通 muted 色 */}
        <span className={thinkingNow ? 'copilot-shimmer' : undefined}>
          {thinkingNow ? '深度思考中…' : `已深度思考（${thinking.length} 字）`}
        </span>
      </summary>
      <pre className="mt-1.5 max-h-56 overflow-y-auto border-t border-border pt-1.5 text-[11.5px] leading-relaxed break-words whitespace-pre-wrap text-muted-foreground">
        {thinking}
      </pre>
    </details>
  )
})
