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
 *
 * ## 长工具期间的「上游安静 N 秒…」（见 {@link IdleHint}）
 *
 * 活动行只说「在查什么」，说了 3 分钟也还是那一句。工具在后端跑两分钟完全正常
 * （读大目录、批量检索），而这段时间连接上一个字节都没有——不额外说一句，律师
 * 无法判断是「后端在干活」还是「连接死了」。所以超过阈值补一行安静提示。
 *
 * **只提示、绝不中止**（见 domain/stream-guard 的「血的教训」）：上一版拿 90 秒
 * 无字节去 abort，把长工具一律杀在半路，那比转圈糟糕得多。
 */

import { memo, useEffect, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'

import { activityText, currentTool } from '../domain'
import { IdleWatchdog } from '../domain'
import type { ChatMessage } from '../types'

/**
 * 安静提示的刷新步长。
 *
 * 文案只精确到秒，5 秒一查足够；1 秒一查纯属拿渲染换心安（超时阈值在 45 秒量级，
 * 提前 4 秒显示不会有人察觉）。
 */
const IDLE_TICK_MS = 5_000

/**
 * 气泡只能看见「可见活动」（正文/思考/工具的变化），看不见心跳；所以这里两个
 * 时钟同时推进，语义退化为「多久没有可见变化」。真正的逐字节 `touchByte` 留给
 * 流消费层（streaming.ts 手上有每一帧）——那一层还没有展示位，有了再接。
 */
function IdleHint() {
  const [hint, setHint] = useState<string | null>(null)
  const watchdog = useMemo(() => new IdleWatchdog(), [])

  useEffect(() => {
    const id = setInterval(() => {
      // 同文案时 setState 会 bail out，不会每秒重渲染一次
      setHint(watchdog.check())
    }, IDLE_TICK_MS)
    return () => clearInterval(id)
  }, [watchdog])

  if (hint === null) return null
  return (
    <span
      className="ml-1 flex-none text-[11px] whitespace-nowrap opacity-70"
      data-testid="stream-idle-hint"
    >
      {hint}
    </span>
  )
}

export const StreamActivity = memo(function StreamActivity({ message }: { message: ChatMessage }) {
  const text = activityText(message)
  if (text === null) return null
  const tool = currentTool(message)
  // 活动一变（换了工具 / 工具回来了 / 正文开始）就重挂安静提示：计时必须从**这次**
  // 活动算起，否则前一个工具等待的时间会被算到下一个工具头上，安静提示提早出现。
  const activitySignature = `${tool?.id ?? ''}:${tool?.content ? '1' : '0'}:${text}`
  return (
    <div
      className="flex items-center gap-1.5 py-0.5 text-[12px] leading-relaxed text-muted-foreground"
      data-testid="stream-activity"
      // 工具名原样挂在 title 上：律师要核对「到底查的是哪个接口」时能看全名
      title={tool?.toolName}
    >
      <Loader2 className="h-3 w-3 flex-none animate-spin" />
      <span className="copilot-shimmer truncate">{text}</span>
      <IdleHint key={activitySignature} />
    </div>
  )
})
