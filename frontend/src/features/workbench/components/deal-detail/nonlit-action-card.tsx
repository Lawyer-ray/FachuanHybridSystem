/**
 * 非诉 · 阶段执行卡（与诉讼线 `bank-litigation/stages/StageActionCard` 同构）
 *
 * 为什么非诉也需要这个：诉讼线录屏时最有说服力的是「点一下，看机器跑」——
 * 进度条、逐步日志、失败重试、中途要人确认。非诉页原来只能看不能动，
 * 律师点进去没有任何可操作的东西。
 *
 * 这里刻意保持与诉讼线**同样的三段状态与视觉**：
 *   idle(待执行) → running(进度+日志) → awaiting(等人确认) → done/failed
 * 让两条线在观感上是同一套系统，而不是两个产品。
 */

import { AlertTriangle, CheckCircle2, Loader2, Play, RotateCcw, ShieldQuestion, XCircle } from 'lucide-react'

import { cn } from '@/lib/utils'

import { ActionButton, Card } from './ui'
import { useNonLitAction } from './use-nonlit-action'

/**
 * 内嵌块：卡片里再分一层（与诉讼线 InsetBlock 同口径）。
 *
 * 底色块**不画边框**：执行卡本身已经是一张带边框的卡，块再套边框就成了三层
 * 同心矩形，相邻块之间只剩 2.5px 白缝，视觉上会糊成一团。需要真边框时传 `framed`。
 */
function InsetBlock({
  children,
  className,
  framed = false,
}: {
  children: React.ReactNode
  className?: string
  framed?: boolean
}) {
  return (
    <div
      className={cn(
        'rounded-[9px] px-3 py-2',
        framed ? 'border border-border-light bg-background' : 'bg-secondary/35',
        className,
      )}
    >
      {children}
    </div>
  )
}

const LOG_TONE: Record<string, string> = {
  info: 'text-secondary-foreground',
  ok: 'text-status-green',
  warn: 'text-status-yellow',
  error: 'text-status-red',
  sub: 'text-muted-foreground',
}

/** 阶段动作状态机 */
/** 阶段执行卡 UI */
export function NonLitActionCard({
  title,
  desc,
  actionLabel,
  hint,
  state,
}: {
  title: string
  desc: string
  actionLabel: string
  hint?: string
  state: ReturnType<typeof useNonLitAction>
}) {
  const { phase, percent } = state
  const active = phase === 'running' || phase === 'awaiting'

  return (
    /*
     * 包里（某张卡的内部）已经有一圈边框，这里就不该再画第二圈：原来「卡里卡」
     * 双层边框 + 5px 阴影，是这一页看着挤的主因。自报家门用左侧色条 + 浅底。
     */
    <Card
      className={cn(
        'border-0 border-l-[3px] border-l-border px-3.5 py-3 shadow-none',
        phase === 'idle' && 'bg-secondary/30',
        phase === 'done' && 'border-l-status-green/60 bg-status-green-bg/20',
        phase === 'failed' && 'border-l-status-red/60 bg-status-red-bg/20',
        phase === 'awaiting' && 'border-l-status-yellow bg-status-yellow-bg/25',
      )}
    >
      <div className="flex flex-wrap items-start gap-3.5">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-[620]">{title}</span>
            {state.retries > 0 ? (
              <span className="rounded-[4px] bg-status-yellow-bg px-1.5 py-[1px] text-[9.5px] font-medium text-status-yellow">
                已重试 {state.retries} 次
              </span>
            ) : null}
            {state.stepIndex > 0 && active ? (
              <span className="text-[10px] tabular-nums text-muted-foreground">第 {state.stepIndex} 步</span>
            ) : null}
          </div>
          <p className="mt-1 max-w-[560px] text-[11.5px] leading-[1.65] text-muted-foreground">{desc}</p>
        </div>

        <div className="flex flex-none flex-col items-end gap-1.5">
          {phase === 'idle' ? (
            <>
              <ActionButton dark onClick={() => void state.execute()}>
                <Play className="size-3.5" /> {actionLabel}
              </ActionButton>
              {hint ? <span className="text-[10px] text-muted-foreground">{hint}</span> : null}
            </>
          ) : null}
          {phase === 'running' ? (
            <>
              <span className="inline-flex h-[31px] items-center gap-1.5 rounded-[8px] border border-foreground bg-foreground px-[13px] text-[12.5px] font-semibold text-background opacity-60">
                <Loader2 className="size-3.5 animate-spin" /> 执行中 {percent}%
              </span>
              <span className="max-w-[200px] truncate text-[10px] text-muted-foreground" title={state.progress}>
                {state.progress}
              </span>
            </>
          ) : null}
          {phase === 'awaiting' ? (
            <>
              <ActionButton dark onClick={state.confirm}>
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
              <ActionButton onClick={state.reset}>
                <RotateCcw className="size-3" /> 重新执行
              </ActionButton>
            </>
          ) : null}
          {phase === 'failed' ? (
            <>
              <div className="flex items-center gap-1.5 text-[12px] font-medium text-status-red">
                <XCircle className="size-3.5" /> 执行失败
              </div>
              <ActionButton onClick={() => void state.execute()}>
                <RotateCcw className="size-3" /> 重试
              </ActionButton>
            </>
          ) : null}
        </div>
      </div>

      {active || phase === 'done' ? (
        <div className="mt-2.5">
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

      {state.log.length > 0 ? (
        <InsetBlock className="mt-2.5 bg-secondary/25">
          <ul className="flex max-h-[200px] flex-col gap-[3px] overflow-y-auto">
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

      {phase === 'done' ? (
        <InsetBlock className="mt-2 border-status-green/40 bg-status-green-bg/60">
          <div className="text-[11.5px] font-medium text-status-green">{state.summary}</div>
        </InsetBlock>
      ) : null}
    </Card>
  )
}
