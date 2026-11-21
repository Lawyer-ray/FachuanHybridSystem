/**
 * 轮次大纲（长会话导航）：竖排「轮号 + 问题预览 + 时间」。
 *
 * 纯展示组件：**不操作滚动、不查 DOM**。当前轮由宿主按滚动位置算好传
 * `activePromptId`，点击也只回调 `onJump(promptId)`——跳转实现（scrollIntoView /
 * 定位到哪条气泡）归宿主，组件不猜转录结构。
 */

import { formatClock } from '../domain'
import type { TurnOutline } from '../domain'

export interface TurnRailProps {
  /** `buildTurnOutline(messages)` 的结果（与转录同一窗口） */
  turns: TurnOutline[]
  /** 当前轮的用户消息 id；null/undefined = 不高亮 */
  activePromptId?: string | null
  /** 跳到某一轮：messageId 即该轮的 `promptId`（该条 user 消息） */
  onJump: (messageId: string) => void
  /** 外层定位/宽度由宿主给（如 `absolute right-2 top-3 w-56`） */
  className?: string
}

/** 超过这个轮数才内部滚动，短会话不出现第二条滚动条 */
const SCROLL_AFTER = 12

export function TurnRail({ turns, activePromptId, onJump, className = '' }: TurnRailProps) {
  if (turns.length === 0) return null
  return (
    <nav
      aria-label="轮次大纲"
      className={`flex flex-col rounded-[10px] border border-border bg-card/95 p-1 shadow-sm ${
        turns.length > SCROLL_AFTER ? 'max-h-[60vh] overflow-y-auto overscroll-contain' : ''
      } ${className}`}
    >
      <ol className="flex flex-col gap-0.5">
        {turns.map((turn) => {
          const active = turn.promptId === activePromptId
          return (
            <li key={turn.promptId}>
              <button
                type="button"
                onClick={() => onJump(turn.promptId)}
                aria-current={active ? 'true' : undefined}
                title={`第 ${turn.turn} 轮${turn.agents.length > 0 ? ` · ${turn.agents.join(' / ')}` : ''}\n${turn.preview}`}
                className={`flex w-full items-center gap-1.5 rounded-[7px] px-1.5 py-1 text-left text-[11.5px] transition-colors ${
                  active
                    ? 'bg-secondary font-medium text-foreground'
                    : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground'
                }`}
              >
                <span className="w-5 flex-none text-right tabular-nums">{turn.turn}</span>
                <span className="min-w-0 flex-1 truncate">{turn.preview || '（无内容）'}</span>
                {turn.at ? (
                  <time
                    className="flex-none text-[10.5px] text-muted-foreground tabular-nums"
                    dateTime={new Date(turn.at).toISOString()}
                    title={new Date(turn.at).toLocaleString('zh-CN')}
                  >
                    {formatClock(turn.at)}
                  </time>
                ) : null}
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
