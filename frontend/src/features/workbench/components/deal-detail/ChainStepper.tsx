import { Fragment } from 'react'

import type { ChainStep } from './detail-domain'
import { Card, StateDot } from './ui'

/**
 * 程序链 stepper：合同勾选的阶段 ∪ 实际案件阶段，按程序序一屏看清「到哪了」——
 * 已结 ● / 在办 ◎ / 未启动 ◌；同阶段多案（分叉）标 ×N。点击滚到该阶段首个案件节，未启动不可点。
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
    <Card className="mb-[18px] flex overflow-x-auto px-5 py-[13px] max-[680px]:px-3.5">
      {/* 内容整体居中：超宽屏下不再「节点贴左、摘要飘到另一端」 */}
      <div className="mx-auto flex min-w-max items-center">
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
                </span>
                {s.n > 1 && <span className="ml-0.5 text-[10px] font-semibold text-muted-foreground/70 tabular-nums">×{s.n}</span>}{' '}
                <span className="text-[11px] whitespace-nowrap text-muted-foreground/80 tabular-nums">{s.sub}</span>
              </span>
            </button>
          </Fragment>
        ))}
        {summary && (
          <span className="ml-6 flex-none text-xs whitespace-nowrap text-muted-foreground tabular-nums">{summary}</span>
        )}
      </div>
    </Card>
  )
}
