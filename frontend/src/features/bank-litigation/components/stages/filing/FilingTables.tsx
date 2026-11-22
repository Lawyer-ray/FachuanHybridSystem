/**
 * ⑥ 校验的左列三张核对表：签字盖章 / 起诉条件 / 不通过项怎么修。
 *
 * 三张表都是**只读呈现**（点行开抽屉、或者只显示口径），不是面板的编排。
 * 抽出来后 `FilingPanel` 只剩「统计 → 三张表 → 通知卡 → 右栏 → 两个抽屉」。
 */

import { CheckCircle2, XCircle } from 'lucide-react'

import { cn } from '@/lib/utils'

import { ClickableRow } from '../../ClickableRow'
import { DEMO_FILING_CHECKS, DEMO_FILING_FIXES, DEMO_SIGN_CHECKS } from '../../demo-data'
import { ActionButton, Pill, SectionTitle, WorkCard } from '../../ui'
import type { ActionPhase } from '../use-stage-action'

/** 签字盖章核对：机器比对扫描件的印章与签名区域，点行看单份明细 */
export function SignCheckTable({
  blockedCount,
  onOpen,
}: {
  /** 未通过份数（面板顶部统计与右栏用的是同一份数，从这里传进来避免两处各算一遍） */
  blockedCount: number
  onOpen: (docName: string) => void
}) {
  return (
      <WorkCard padded={false}>
        <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
          <SectionTitle
            title="签字盖章核对"
            hint="机器比对扫描件的印章与签名区域 · 可逐份复核"
            className="w-full"
            action={<Pill tone={blockedCount ? 'red' : 'green'}>未通过 {blockedCount}</Pill>}
          />
        </div>
        <ul className="divide-y divide-border-light">
          {DEMO_SIGN_CHECKS.map((d) => {
            const ok = d.sealOk && d.signOk
            return (
              <ClickableRow
                key={d.docName}
                onClick={() => onOpen(d.docName)}
                className="flex items-start gap-3 px-5 py-3"
              >
                <span
                  className={cn(
                    'mt-[3px] grid size-4 flex-none place-items-center rounded-full',
                    ok ? 'bg-status-green' : 'bg-status-red',
                  )}
                >
                  {ok ? (
                    <CheckCircle2 className="size-2.5 text-white" strokeWidth={3} />
                  ) : (
                    <XCircle className="size-2.5 text-white" strokeWidth={3} />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[12.5px] font-medium">{d.docName}</div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[10.5px] text-muted-foreground">
                    <span>需盖：{d.needSeal}</span>
                    {d.needSign !== '—' ? (
                      <>
                        <span className="text-border">·</span>
                        <span>需签：{d.needSign}</span>
                      </>
                    ) : null}
                  </div>
                  <div
                    className={cn(
                      'mt-0.5 text-[10.5px]',
                      ok ? 'text-muted-foreground' : 'text-status-red',
                    )}
                  >
                    {d.note}
                  </div>
                </div>
                <div className="flex flex-none items-center gap-1.5">
                  <Pill tone={d.sealOk ? 'green' : 'red'}>章{d.sealOk ? '✓' : '✗'}</Pill>
                  <Pill tone={d.signOk ? 'green' : 'red'}>签{d.signOk ? '✓' : '✗'}</Pill>
                </div>
              </ClickableRow>
            )
          })}
        </ul>
      </WorkCard>
  )
}

/** 起诉条件机器判定：法律要件 + 卷宗要件 */
export function CheckResultTable() {
  return (
      <WorkCard padded={false}>
        <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
          <SectionTitle title="起诉条件机器判定" hint="法律要件 + 卷宗要件" className="w-full" />
        </div>
        <ul className="divide-y divide-border-light">
          {DEMO_FILING_CHECKS.map((c) => (
            <li key={c.check} className="flex items-start gap-3 px-5 py-2.5">
              <span
                className={
                  c.result === 'pass'
                    ? 'mt-[3px] grid size-4 flex-none place-items-center rounded-full bg-status-green'
                    : c.result === 'warn'
                      ? 'mt-[3px] grid size-4 flex-none place-items-center rounded-full bg-status-yellow'
                      : 'mt-[3px] grid size-4 flex-none place-items-center rounded-full bg-status-red'
                }
              >
                <span className="text-[9px] font-bold text-white">
                  {c.result === 'pass' ? '✓' : c.result === 'warn' ? '!' : '✕'}
                </span>
              </span>
              <span className="w-[110px] flex-none text-[12px] font-medium">{c.check}</span>
              <span className="w-[160px] flex-none truncate text-[11px] text-muted-foreground" title={c.value}>{c.value}</span>
              <span className="min-w-0 flex-1 truncate text-[10.5px] text-muted-foreground" title={c.detail}>{c.detail}</span>
              <Pill tone={c.result === 'pass' ? 'green' : c.result === 'warn' ? 'yellow' : 'red'}>
                {c.result === 'pass' ? '通过' : c.result === 'warn' ? '提示' : '不通过'}
              </Pill>
            </li>
          ))}
        </ul>
      </WorkCard>
  )
}

/** 不通过项怎么修：系统能自动修的会先给看 diff，律师确认后才执行 */
export function FixSuggestionTable({
  autoFixPhase,
  autoFixSummary,
  onOpenDiff,
}: {
  autoFixPhase: ActionPhase
  autoFixSummary: string
  onOpenDiff: () => void
}) {
  return (
      <WorkCard padded={false}>
        <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
          <SectionTitle
            title="不通过项怎么修"
            hint="系统能自动修的会先给你看 diff"
            className="w-full"
            action={
              <ActionButton sm dark disabled={autoFixPhase === 'running'} onClick={() => onOpenDiff()}>
                {autoFixPhase === 'running' ? '修正中…' : autoFixPhase === 'done' ? '已修正 · 再看 diff' : '一键修正可自动项'}
              </ActionButton>
            }
          />
        </div>
        <ul className="divide-y divide-border-light">
          {DEMO_FILING_FIXES.map((f) => (
            <li key={f.item} className="px-5 py-2.5">
              <div className="flex items-center gap-2">
                <span className="text-[12px] font-medium">{f.item}</span>
                <Pill tone={f.auto ? 'green' : 'yellow'}>{f.auto ? '系统自动' : '需人工'}</Pill>
                {f.auto && autoFixPhase === 'done' ? <Pill tone="blue">已修正</Pill> : null}
                <span className="ml-auto text-[10px] text-muted-foreground">{f.owner} · {f.eta}</span>
              </div>
              <div className="mt-0.5 text-[10.5px] text-muted-foreground">{f.fix}</div>
            </li>
          ))}
        </ul>
        {autoFixPhase === 'done' ? (
          <div className="border-t border-border-light bg-status-green-bg/30 px-5 py-2 text-[10.5px] text-status-green">
            {autoFixSummary}
          </div>
        ) : null}
      </WorkCard>
  )
}
