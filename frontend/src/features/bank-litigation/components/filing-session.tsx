/* eslint-disable react-refresh/only-export-components */
/**
 * 立案会话的共用呈现：轮询阶段文案 + 会话结果块。
 *
 * ═══ 为什么单独一个文件 ═══
 * OA 立案（`oa/OAFilingPanel.tsx`）与一张网（`FilingPanels.tsx`）的会话形状完全相同：
 * 提交 → 后台跑 → 轮询 → 终态停。两侧共用这套阶段文案与结果块，
 * 但 react-refresh 规则不允许一个「组件文件」再导出常量/纯函数，
 * 所以把共用部分收在这里，两个面板各自 import。
 * 本文件同时导出常量/纯函数与一个小组件，fast-refresh 规则按
 * `components/shared/status-badge.tsx` 的同样取舍在文件级关闭（改本文件时整页刷新）。
 */

import { StatusBadge, type Tone } from '@/components/shared/status-badge'
import { cn } from '@/lib/utils'

import type { AutoPhase } from '../hooks/use-auto-run'

/** 轮询阶段 → 语气与文案 */
export const PHASE_META: Record<AutoPhase, { tone: Tone; text: string }> = {
  idle: { tone: 'neutral', text: '待启动' },
  submitting: { tone: 'blue', text: '正在提交' },
  running: { tone: 'blue', text: '执行中' },
  done: { tone: 'neutral', text: '已结束' },
  timeout: { tone: 'yellow', text: '等待超时' },
}

/** StatusBadge 的 Tone 含 purple，Pill 不收 —— 进度语气只会用到这五种，窄化一次 */
export function pillTone(t: Tone): 'neutral' | 'green' | 'red' | 'yellow' | 'blue' {
  return t === 'purple' ? 'neutral' : t
}

/** 会话状态 → 语气。后端 status 字符串大小写/取值不完全统一，按语义归类。 */
function sessionTone(status: string): Tone {
  const s = (status || '').toLowerCase()
  if (s === 'success' || s === 'finished' || s === 'completed') return 'green'
  if (s === 'failed' || s === 'error') return 'red'
  if (s === 'running' || s === 'pending' || s === 'processing') return 'blue'
  return 'neutral'
}

/**
 * 会话结果块。两个面板共用：
 * 失败原因（error）、后端原始 status、超时提醒，是同一套呈现。
 */
export function SessionResult({
  error,
  status,
  phase,
  hint,
}: {
  error: string | null
  status: string
  phase: AutoPhase
  hint: string
}) {
  if (phase === 'idle') return null

  return (
    <div className="rounded-[7px] border border-border bg-secondary/30 px-2.5 py-1.5">
      <div className="flex items-center gap-2 text-[11.5px]">
        <span className="text-muted-foreground">会话状态</span>
        <StatusBadge tone={sessionTone(status)} size="xs">
          {status || '（未返回）'}
        </StatusBadge>
      </div>
      {error ? (
        <p className="mt-1 text-[11.5px] leading-[1.6] text-status-red">
          {hint}失败：{error}
        </p>
      ) : null}
      {phase === 'timeout' ? (
        <p className={cn('mt-1 text-[11.5px] leading-[1.6] text-status-yellow')}>
          等待超过 15 分钟仍未结束。任务可能仍在后台运行 —— 稍后回本页刷新查看，
          或到 OA / 一张网里确认实际结果，不要重复提交。
        </p>
      ) : null}
    </div>
  )
}
