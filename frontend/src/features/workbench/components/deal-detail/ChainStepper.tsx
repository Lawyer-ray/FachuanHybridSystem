import { Fragment } from 'react'

import type { ChainStep } from './detail-domain'
import { Card, StateDot } from './ui'

/**
 * 程序链 stepper：一屏看清「到哪了」——已结 ● / 在办 ◎ / 未启动 ◌，
 * 点击滚动到对应案件节（执行虚节点不可点）。窄屏横向滚动。
 */
export function ChainStepper({
  steps,
  summary,
  onJump,
}: {
  steps: ChainStep[]
  summary: string
  onJump: (caseId: number) => void
}) {
  return (
    <Card className="mb-[18px] flex items-center overflow-x-auto px-5 py-[13px] max-[680px]:px-3.5">
      {steps.map((s, i) => (
        <Fragment key={s.key}>
          {i > 0 && <span className="mx-1.5 h-px w-[34px] flex-none bg-border" />}
          <button
            type="button"
            disabled={s.caseId == null}
            title={s.caseId == null ? '未启动' : '跳到 ' + s.stage}
            className={
              'flex flex-none items-center gap-[9px] rounded-[8px] px-1.5 py-1 text-left transition-colors ' +
              (s.caseId == null ? 'cursor-default' : 'hover:bg-secondary')
            }
            onClick={() => s.caseId != null && onJump(s.caseId)}
          >
            <StateDot state={s.state} />
            <span className="whitespace-nowrap">
              <span className={'text-[13.5px] tracking-[-0.01em] ' + (s.state === 'todo' ? 'font-medium text-muted-foreground' : 'font-[620] text-foreground')}>
                {s.stage}
              </span>{' '}
              <span className="text-[11px] whitespace-nowrap text-muted-foreground/80 tabular-nums">{s.sub}</span>
            </span>
          </button>
        </Fragment>
      ))}
      {summary && (
        <span className="ml-auto flex-none pl-4 text-xs whitespace-nowrap text-muted-foreground tabular-nums">{summary}</span>
      )}
    </Card>
  )
}
