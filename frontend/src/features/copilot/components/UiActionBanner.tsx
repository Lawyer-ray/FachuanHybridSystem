/**
 * 「AI 正在操作」横幅：把界面动作（`ui_action`）的执行态摆在律师眼前。
 *
 * ## 为什么必须有这条可见状态
 *
 * 执行结果**不回传模型**（T1 单向指令，08 §3.1），也**不进转录**
 * （理由见 store/ui-tools.ts 文件头）。没有横幅的话，AI 让页面跳一下就只剩「页面
 * 自己动了」——律师会怀疑是自己误触；失败时更糟：页面上什么都没发生，而 AI 已经在
 * 对话里说「已为你打开」。
 *
 * ## 为什么「停下」只挡后续动作
 *
 * 软打断的粒度是「同一 run 的后续 ui_action」（08 §4.5）：动作在毫秒内就落完了，
 * 追回没有意义。真要中止后端生成，用输入框上方现有的停止键（关流）。
 *
 * ## 多栏前缀为什么读 answerAgents、agent 为什么要外部传
 *
 * 08 §9 要求 `columnCount > 1` 时标来源。但 `columnCount` 只是本轮开流时处理器闭包里
 * 的一个数（`handlers/context.ts`），不进 store；store 里同一件事的唯一可读快照是
 * `answerAgents`（本轮勾了几栏）。而「这条动作来自哪一栏」需要 T1 帧把 `agent` 带进
 * `UiActionRequest`——当前冻结契约只有 4 个字段，所以来源由挂载点作为可选 prop 补齐；
 * 空串 = 不标（与 `handlers/approval-question.ts` 的 laneAgent 同口径）。
 */

import { useEffect, useState } from 'react'

import { UI_TOOL_SPECS } from '../ui-tools'
import { useCopilot } from '../store'
import type { CopilotState } from '../types'

/** 终态停留多久再淡出：落完就消失，律师会以为「什么都没发生」 */
const OK_HOLD_MS = 1_200
/** 淡出时长（与下面 className 的 duration-300 同值） */
const FADE_MS = 300

/** shown = 正常显示；fading = 正在淡出；gone = 已从 DOM 移除 */
type Phase = 'shown' | 'fading' | 'gone'

/** 动作名 → 中文名；未知动作回落原名（「AI 操作了 ui_xxx」比一行空白更可诊断） */
function titleOf(action: string): string {
  return UI_TOOL_SPECS.find((spec) => spec.name === action)?.title ?? action
}

/** 只呈现最近一次动作：先前那条已被下一次覆盖（last-writer-wins，08 §9） */
function latestRun(runs: CopilotState['uiToolRuns']): { callId: string; run: CopilotState['uiToolRuns'][string] } | null {
  let latest: { callId: string; run: CopilotState['uiToolRuns'][string] } | null = null
  for (const [callId, run] of Object.entries(runs)) {
    if (latest === null || run.startedAt >= latest.run.startedAt) latest = { callId, run }
  }
  return latest
}

const VERB: Record<CopilotState['uiToolRuns'][string]['state'], string> = {
  pending: 'AI 正在操作',
  running: 'AI 正在操作',
  ok: 'AI 已完成',
  error: 'AI 操作失败',
  aborted: 'AI 操作已取消',
}

export function UiActionBanner({ agent = '' }: { agent?: string }) {
  const runs = useCopilot((s) => s.uiToolRuns)
  const multiLane = useCopilot((s) => s.answerAgents.length > 1)
  const abortUiActions = useCopilot((s) => s.abortUiActions)
  const latest = latestRun(runs)
  const [phase, setPhase] = useState<Phase>('shown')

  // 终态（ok / aborted）停 OK_HOLD_MS 再淡出；失败**不**淡出——失败必须留得住，
  // 直到下一次动作把它顶掉（配合 store 的 toast，两处都看得见）。
  const terminalKey = latest !== null && (latest.run.state === 'ok' || latest.run.state === 'aborted') ? latest.callId : null
  useEffect(() => {
    setPhase('shown')
    if (terminalKey === null) return
    const fade = window.setTimeout(() => setPhase('fading'), OK_HOLD_MS)
    const gone = window.setTimeout(() => setPhase('gone'), OK_HOLD_MS + FADE_MS)
    return () => {
      window.clearTimeout(fade)
      window.clearTimeout(gone)
    }
  }, [terminalKey])

  if (latest === null || phase === 'gone') return null

  const { run } = latest
  const inFlight = run.state === 'pending' || run.state === 'running'
  const failed = run.state === 'error'

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="ui-action-banner"
      className={[
        'flex items-center gap-2 rounded-[9px] border px-2.5 py-1.5 text-[12px] transition-opacity duration-300',
        failed
          ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300'
          : 'border-border bg-card text-foreground',
        phase === 'fading' ? 'opacity-0' : 'opacity-100',
      ].join(' ')}
    >
      <span className="min-w-0 flex-1 truncate">
        {multiLane && agent ? `${agent}：` : ''}
        {VERB[run.state]}：{titleOf(run.name)}
      </span>
      {inFlight && (
        <button
          type="button"
          onClick={abortUiActions}
          className="flex-none rounded-[6px] px-1.5 py-0.5 text-[11.5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          停下
        </button>
      )}
    </div>
  )
}
