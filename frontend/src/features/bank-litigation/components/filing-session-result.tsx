/**
 * 立案会话的结果块：两个立案面板（一张网 / 律所 OA）共用。
 *
 * ═══ 为什么单独一个文件 ═══
 * OA 立案（`oa/OAFilingPanel.tsx`）与一张网（`CourtFilingPanel.tsx`）的会话形状完全相同：
 * 提交 → 后台跑 → 轮询 → 终态停。结果块两侧共用，所以抽成单组件文件，
 * 两个面板各自 import；轮询阶段的文案与语气在 `constants.ts`（`PHASE_META` / `pillTone`）。
 */

import { StatusBadge, type Tone } from '@/components/shared/StatusBadge'
import { cn } from '@/lib/utils'

import type { AutoPhase } from '../hooks/use-auto-run'

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
