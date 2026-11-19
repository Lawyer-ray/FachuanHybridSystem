/**
 * 「这个 agent 此刻在干什么」的呼吸行——挂在**本栏气泡内**、正文之前。
 *
 * 真实反馈（三栅截图）：Pi 2.4 秒就出字（边调工具边吐过程），dsh / openai-agents
 * 却是「憋到 16 秒才一次性吐全文」。根因不在网关（0.28s 就有 chunk），而在这两个
 * 后端**先调工具、调完才说正文**，其间界面一片空白——律师只能看到三个 agent 速度
 * 不一样，看到的是「卡死」。
 *
 * 事件链路本来就通（`tool_call` → 工具行 → `ToolRow`），问题全在**位置和措辞**：
 * 工具行原先渲染在气泡之外的转录流里，用户注意力在正文区，看不到；「调用中」也没
 * 说清在干什么。这里把「正在查 XX…」放进气泡本身，并用 `copilot-shimmer` 流光
 * 表明还活着（同一套动效，`prefers-reduced-motion` 下自动回落为静态文字）。
 *
 * 工具条**只有一个可见位置**：正文没到 → 气泡内的活动行（本组件，显示当前动作）；
 * 正文到了 → 气泡下方的紧凑 chip（ToolChips，显示查过的清单）。两者按「正文有没有
 * 到」互斥，不会重复渲染成两处。
 *
 * 思考中的情形不归这里管：思考块自己的「深度思考中…」就是活着的证据，再叠一行
 * 只会读成两条状态。
 */

import { memo } from 'react'
import { Loader2 } from 'lucide-react'

import { activityText, pendingToolCall } from '../domain'
import type { ChatMessage } from '../types'

export const StreamActivity = memo(function StreamActivity({ message }: { message: ChatMessage }) {
  const text = activityText(message)
  if (text === null) return null
  const pending = pendingToolCall(message.tools)
  return (
    <div
      className="flex items-center gap-1.5 py-0.5 text-[12px] leading-relaxed text-muted-foreground"
      data-testid="stream-activity"
      // 工具名原样挂在 title 上：律师要核对「到底查的是哪个接口」时能看全名
      title={pending?.toolName}
    >
      <Loader2 className="h-3 w-3 flex-none animate-spin" />
      <span className="copilot-shimmer truncate">{text}</span>
    </div>
  )
})
