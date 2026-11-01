/**
 * 阶段执行卡：每个阶段顶部的「主操作」区域。
 *
 * ═══ 为什么放在最上面 ═══
 * 演示时律师打开一个阶段，第一个问题永远是「我现在该干什么」。
 * 所以按钮必须在最显眼的位置，而不是埋在表格下面。
 *
 * 三种呈现：
 *   idle    → 一句「这个阶段做什么」+ 主按钮
 *   running → 进度文案 + 逐行日志（让观众看到系统在干活）
 *   done    → 结果摘要 + 「重新执行」
 *   failed  → 失败原因 + 「重试」
 */

import { CheckCircle2, Loader2, Play, RotateCcw, XCircle } from 'lucide-react'

import { cn } from '@/lib/utils'

import type { StageActionState } from './use-stage-action'
import { ActionButton, InsetBlock, WorkCard } from '../ui'

export function StageActionCard({
  title,
  desc,
  actionLabel,
  state,
  execute,
  reset,
  hint,
}: {
  title: string
  desc: string
  actionLabel: string
  state: StageActionState
  execute: () => void
  reset: () => void
  /** 按钮旁的补充说明（如「预计 30 秒」） */
  hint?: string
}) {
  const { phase } = state

  return (
    <WorkCard
      className={cn(
        phase === 'done' && 'border-status-green/40 bg-status-green-bg/30',
        phase === 'failed' && 'border-status-red/40 bg-status-red-bg/30',
      )}
    >
      <div className="flex flex-wrap items-start gap-4">
        {/* 左：标题与说明 */}
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-[620]">{title}</div>
          <p className="mt-1 max-w-[560px] text-[11.5px] leading-[1.65] text-muted-foreground">{desc}</p>
        </div>

        {/* 右：动作 */}
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
                <Loader2 className="size-3.5 animate-spin" /> 执行中…
              </ActionButton>
              <span className="max-w-[180px] truncate text-[10px] text-muted-foreground" title={state.progress}>
                {state.progress}
              </span>
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

      {/* 执行日志：running/done/failed 时展开 */}
      {state.log.length > 0 ? (
        <InsetBlock className="mt-3 bg-secondary/25">
          <ul className="flex flex-col gap-1">
            {state.log.map((l, i) => (
              <li key={`${l.at}-${i}`} className="flex items-start gap-2 text-[10.5px] leading-[1.6]">
                <span className="flex-none tabular-nums text-muted-foreground">{l.at}</span>
                <span
                  className={cn(
                    'min-w-0 flex-1 break-words',
                    l.ok === false ? 'text-status-red' : l.ok === true ? 'text-status-green' : 'text-secondary-foreground',
                  )}
                >
                  {l.text}
                </span>
              </li>
            ))}
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
