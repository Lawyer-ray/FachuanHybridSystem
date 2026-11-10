/**
 * 关厂清盘 · 风险登记表 + 客户确认记录（两张卡共用一份筛选状态）
 *
 * 关厂清盘里「哪些事可能炸、炸了怎么办、谁盯着」和「客户哪天点了头」是律师
 * 最常被追问的两张表。以前一页里只有阶段和交付物，这两件事一个字都没有。
 *
 * 风险卡默认只列**未闭环**的（已闭环的折起来），因为录屏时观众要看的是
 * 「还剩几颗雷」；客户确认卡按时间倒序，一眼看清最近一次确认是什么结论。
 */

import { useState } from 'react'
import { BadgeCheck, ShieldAlert } from 'lucide-react'

import { cn } from '@/lib/utils'

import { DEMO_NL1_CLIENT_CONFIRMS, DEMO_NL1_RISKS, type DemoNl1ClientConfirm, type DemoNl1Risk } from '../../demo-nonlit'
import { Card } from '../../ui'
import { BlockHead, EmptyHint, Inset, TonePill, type Tone } from './special-bits'

const LEVEL_TONE: Record<DemoNl1Risk['level'], Tone> = { 高: 'red', 中: 'yellow', 低: 'neutral' }
const RISK_STATUS_TONE: Record<DemoNl1Risk['status'], Tone> = { 待决断: 'red', 监控中: 'blue', 已闭环: 'green' }
const VERDICT_TONE: Record<DemoNl1ClientConfirm['verdict'], Tone> = {
  确认: 'green',
  附条件确认: 'yellow',
  不确认: 'red',
}

export function SpecialRiskCard({
  risks = DEMO_NL1_RISKS,
  onAssess,
}: {
  risks?: DemoNl1Risk[]
  /** 点风险行的「评估」→ 触发风险复评动作 */
  onAssess: (riskId: string) => void
}) {
  const [showClosed, setShowClosed] = useState(false)
  const [picked, setPicked] = useState<string | null>(risks.find((r) => r.level === '高')?.id ?? null)

  const visible = showClosed ? risks : risks.filter((r) => r.status !== '已闭环')
  const high = risks.filter((r) => r.level === '高' && r.status !== '已闭环').length
  const pending = risks.filter((r) => r.status === '待决断').length

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex items-baseline gap-2">
        <h3 className="flex items-center gap-1.5 text-[13px] font-[620]">
          <ShieldAlert className="size-3.5 text-muted-foreground" />
          风险登记表
        </h3>
        <span className="text-[11px] text-muted-foreground">
          高 {high} 条 · 待决断 {pending} 条 · 共 {risks.length} 条
        </span>
        <button
          type="button"
          onClick={() => setShowClosed((v) => !v)}
          className="ml-auto text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        >
          {showClosed ? '只看未闭环' : '显示已闭环'}
        </button>
      </div>

      <div className="mt-3 flex flex-col overflow-hidden rounded-[9px] border border-border-light bg-background">
        {visible.map((r) => {
          const open = picked === r.id
          return (
            <div
              key={r.id}
              className={cn(
                'border-b border-border-light transition-colors last:border-b-0',
                /* 高风险用左侧色条标出来，不再给整行套一圈红边（会与列表外框叠成双线） */
                r.level === '高' && r.status !== '已闭环' && 'border-l-[3px] border-l-status-red/50',
              )}
            >
              <button
                type="button"
                onClick={() => setPicked(open ? null : r.id)}
                className="flex w-full items-center gap-2 px-3 py-2.5 text-left hover:bg-secondary/35"
              >
                <TonePill tone={LEVEL_TONE[r.level]}>{r.level}</TonePill>
                <span className="min-w-0 flex-1 truncate text-[12.5px] font-[550]" title={r.risk}>
                  {r.risk}
                </span>
                <span className="flex-none text-[10.5px] text-muted-foreground">{r.owner}</span>
                <span className="w-[52px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">{r.due}</span>
                <TonePill tone={RISK_STATUS_TONE[r.status]}>{r.status}</TonePill>
              </button>
              {open ? (
                <div className="border-t border-border-light px-3 py-2.5">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Inset>
                      <div className="text-[10px] text-muted-foreground">影响</div>
                      <div className="mt-0.5 text-[11.5px] leading-[1.6]">{r.impact}</div>
                    </Inset>
                    <Inset>
                      <div className="text-[10px] text-muted-foreground">应对</div>
                      <div className="mt-0.5 text-[11.5px] leading-[1.6]">{r.response}</div>
                    </Inset>
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-[10.5px] text-muted-foreground">
                      责任人 {r.owner} · 到期 {r.due}
                    </span>
                    <button
                      type="button"
                      onClick={() => onAssess(r.id)}
                      className="ml-auto text-[11px] text-muted-foreground underline underline-offset-3 transition-colors hover:text-foreground"
                    >
                      重新评估
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          )
        })}
        {visible.length === 0 ? <EmptyHint>未闭环风险已清空</EmptyHint> : null}
      </div>
    </Card>
  )
}

export function SpecialConfirmCard({ records = DEMO_NL1_CLIENT_CONFIRMS }: { records?: DemoNl1ClientConfirm[] }) {
  const [channel, setChannel] = useState<DemoNl1ClientConfirm['channel'] | 'all'>('all')
  const rows = channel === 'all' ? records : records.filter((r) => r.channel === channel)
  const okCount = records.filter((r) => r.verdict === '确认').length
  const pendingCount = records.filter((r) => r.verdict !== '确认').length

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex items-baseline gap-2">
        <h3 className="flex items-center gap-1.5 text-[13px] font-[620]">
          <BadgeCheck className="size-3.5 text-muted-foreground" />
          客户确认记录
        </h3>
        <span className="text-[11px] text-muted-foreground">
          确认 {okCount} 条 · 待跟进 {pendingCount} 条
        </span>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        {(['all', '邮件', '会议纪要', '签字页', '微信'] as const).map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setChannel(c)}
            className={cn(
              'rounded-[6px] border px-2 py-[2px] text-[11px] transition-colors',
              channel === c
                ? 'border-foreground bg-foreground text-background'
                : 'border-border-light bg-background text-muted-foreground hover:bg-secondary',
            )}
          >
            {c === 'all' ? '全部' : c}
          </button>
        ))}
      </div>

      <div className="mt-3 flex flex-col gap-2">
        {rows.map((r) => (
          <Inset key={r.id}>
            <div className="flex items-center gap-2">
              <TonePill tone={VERDICT_TONE[r.verdict]}>{r.verdict}</TonePill>
              <span className="text-[10.5px] tabular-nums text-muted-foreground">{r.at}</span>
              <span className="rounded-[4px] bg-secondary px-1.5 py-[1px] text-[10px] text-secondary-foreground">{r.channel}</span>
              <span className="ml-auto truncate text-[10.5px] text-muted-foreground">{r.phase}</span>
            </div>
            <div className="mt-1 text-[12px] leading-[1.6]">{r.what}</div>
            <div className="mt-0.5 text-[10.5px] text-muted-foreground">{r.by}</div>
          </Inset>
        ))}
        {rows.length === 0 ? <EmptyHint>该渠道还没有确认记录</EmptyHint> : null}
      </div>

      <div className="mt-3">
        <BlockHead title="推进纪律" hint="未拿到无保留确认前不推进" />
        <div className="text-[10.5px] leading-[1.6] text-muted-foreground">
          「附条件确认」与「不确认」都不计入阶段完成依据；系统在推进到下一阶段时会把它们挑出来。
        </div>
      </div>
    </Card>
  )
}
