/**
 * 阶段执行卡（v2）：进度条 + 日志流 + 中断确认
 *
 * v1 只有「按钮 + 日志」；v2 补上真实系统的三样东西：
 *   ① **进度条**：百分比 + 条纹动画，让人看到还在动（长任务时最重要）
 *   ② **重试角标**：某步失败重试时显示「重试 1/2」，像真系统在纠错
 *   ③ **等待确认**：低头人确认时变黄色卡，按钮换成「确认并继续」
 */

import { AlertTriangle, CheckCircle2, Loader2, Play, RotateCcw, ShieldQuestion, XCircle } from 'lucide-react'

import { cn } from '@/lib/utils'

import type { StageActionState } from './use-stage-action'
import { ActionButton, InsetBlock, WorkCard } from '../ui'

/** 日志行的配色 */
const LOG_TONE: Record<string, string> = {
  info: 'text-secondary-foreground',
  ok: 'text-status-green',
  warn: 'text-status-yellow',
  error: 'text-status-red',
  sub: 'text-muted-foreground',
}

export function StageActionCard({
  title,
  desc,
  actionLabel,
  state,
  execute,
  reset,
  confirm,
  hint,
}: {
  title: string
  desc: string
  actionLabel: string
  state: StageActionState
  execute: () => void
  reset: () => void
  confirm: () => void
  hint?: string
}) {
  const { phase, percent } = state
  const active = phase === 'running' || phase === 'awaiting'

  return (
    <WorkCard
      className={cn(
        phase === 'done' && 'border-status-green/40 bg-status-green-bg/25',
        phase === 'failed' && 'border-status-red/40 bg-status-red-bg/25',
        phase === 'awaiting' && 'border-status-yellow/50 bg-status-yellow-bg/30',
      )}
    >
      <div className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-[620]">{title}</span>
            {state.retries > 0 ? (
              <span className="rounded-[4px] bg-status-yellow-bg px-1.5 py-[1px] text-[9.5px] font-medium text-status-yellow">
                已重试 {state.retries} 次
              </span>
            ) : null}
            {state.stepIndex > 0 && active ? (
              <span className="text-[10px] tabular-nums text-muted-foreground">
                第 {state.stepIndex} 步
              </span>
            ) : null}
          </div>
          <p className="mt-1 max-w-[560px] text-[11.5px] leading-[1.65] text-muted-foreground">{desc}</p>
        </div>

        <div className="flex flex-none flex-col items-end gap-1.5">
          {phase === 'idle' ? (
            <>
              <ActionButton dark onClick={execute}>
                <Play className="size-3.5" /> {actionLabel}
              </ActionButton>
              {hint ? <span className="text-[10px] text-muted-foreground">{hint}</span> : null}
            </>
          ) : null}

          {phase === 'running' ? (
            <>
              <ActionButton dark disabled>
                <Loader2 className="size-3.5 animate-spin" /> 执行中 {percent}%
              </ActionButton>
              <span className="max-w-[200px] truncate text-[10px] text-muted-foreground" title={state.progress}>
                {state.progress}
              </span>
            </>
          ) : null}

          {phase === 'awaiting' ? (
            <>
              <ActionButton dark onClick={confirm}>
                <ShieldQuestion className="size-3.5" /> 确认并继续
              </ActionButton>
              <span className="text-[10px] text-status-yellow">等你确认</span>
            </>
          ) : null}

          {phase === 'done' ? (
            <>
              <div className="flex items-center gap-1.5 text-[12px] font-medium text-status-green">
                <CheckCircle2 className="size-3.5" /> 已完成
              </div>
              <ActionButton onClick={reset}>
                <RotateCcw className="size-3" /> 重新执行
              </ActionButton>
            </>
          ) : null}

          {phase === 'failed' ? (
            <>
              <div className="flex items-center gap-1.5 text-[12px] font-medium text-status-red">
                <XCircle className="size-3.5" /> 执行失败
              </div>
              <ActionButton onClick={execute}>
                <RotateCcw className="size-3" /> 重试
              </ActionButton>
            </>
          ) : null}
        </div>
      </div>

      {/* 进度条：执行中与完成时都有 */}
      {active || phase === 'done' ? (
        <div className="mt-3">
          <div className="h-[5px] overflow-hidden rounded-full bg-secondary">
            <div
              className={cn(
                'h-full rounded-full transition-[width] duration-300 ease-out',
                phase === 'done' ? 'bg-status-green' : phase === 'awaiting' ? 'bg-status-yellow' : 'bg-foreground',
              )}
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      ) : null}

      {/* 等待确认的提示 */}
      {phase === 'awaiting' ? (
        <InsetBlock className="mt-2.5 border-status-yellow/50 bg-status-yellow-bg/60">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-[1px] size-3.5 flex-none text-status-yellow" />
            <div className="min-w-0">
              <div className="text-[11.5px] font-medium">需要你确认</div>
              <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">{state.confirmText}</p>
            </div>
          </div>
        </InsetBlock>
      ) : null}

      {/* 日志 */}
      {state.log.length > 0 ? (
        <InsetBlock className="mt-2.5 bg-secondary/25">
          <ul className="flex max-h-[220px] flex-col gap-[3px] overflow-y-auto">
            {state.log.map((l, i) => (
              <li key={`${l.at}-${i}`} className="flex items-start gap-2 text-[10.5px] leading-[1.55]">
                <span className="flex-none tabular-nums text-muted-foreground">{l.at}</span>
                <span className={cn('min-w-0 flex-1 break-words', LOG_TONE[l.kind ?? 'info'])}>{l.text}</span>
              </li>
            ))}
            {phase === 'running' ? (
              <li className="flex items-center gap-2 text-[10.5px] text-muted-foreground">
                <Loader2 className="size-2.5 animate-spin" />
                <span>{state.progress}…</span>
              </li>
            ) : null}
          </ul>
        </InsetBlock>
      ) : null}

      {phase === 'done' && state.summary ? (
        <InsetBlock className="mt-2 border-status-green/40 bg-status-green-bg/60">
          <div className="text-[11.5px] font-medium text-status-green">{state.summary}</div>
        </InsetBlock>
      ) : null}

      {phase === 'failed' && state.error ? (
        <InsetBlock className="mt-2 border-status-red/40 bg-status-red-bg">
          <div className="text-[11.5px] text-status-red">{state.error}</div>
        </InsetBlock>
      ) : null}
    </WorkCard>
  )
}
