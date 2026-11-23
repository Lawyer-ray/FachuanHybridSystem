import { Loader2 } from 'lucide-react'

import { aggregateStages, dealFacts, dealPayRows, fmtCNDate, lawyerCopyText, partyCopyText } from '../domain'
import type { DealCase, WorkbenchDeal } from '../types'

import { CopyButton } from './CopyButton'
import { MetaRow } from './MetaRow'
import { MoneyCell } from './MoneyCell'
import { SectionTitle } from './SectionTitle'
import { StageNode } from './StageNode'

/**
 * 合同详情抽屉的八个节：金额四格 / 当事人 / 主办律师 / 合同要素 / 收款记录 /
 * 提醒事项 / 补充协议 / 案件。
 *
 * 每节自己判断「本节点没内容」→ 返回 null（空节连标题一起不出现）。整套是纯搬移：
 * class、文案、条件与数据来源与拆前逐字一致，由 `DealSheet.dom.test.tsx` 兜底
 * （每一节都有渲染断言）。
 *
 * 为什么拆出来：DealSheet 一度是 244 行的单函数，九个节串在同一个 return 里，
 * 改「提醒事项」要跨过 200 行去读「补充协议」。
 */

export function MoneySection({ deal }: { deal: WorkbenchDeal }) {
  const hasMoney = deal.amount || deal.totalReceived || deal.totalInvoiced || deal.unpaid
  if (!hasMoney) return null
  return (
    <div className="grid grid-cols-4 gap-1.5 px-6 pt-4">
      <MoneyCell label="律师费" value={deal.amount ?? '—'} />
      <MoneyCell label="已收款" value={deal.totalReceived ?? '—'} />
      <MoneyCell label="已开票" value={deal.totalInvoiced ?? '—'} />
      <MoneyCell label="未收款" value={deal.unpaid ?? '—'} hot />
    </div>
  )
}

export function PartiesSection({ deal }: { deal: WorkbenchDeal }) {
  /* 当事人：我方在前，首个对方行上方留白断组（分组不用标签，角色已表达语义） */
  const sorted = [...deal.partiesAll].sort((a, b) => Number(b.ours) - Number(a.ours))
  const firstOther = sorted.findIndex((p) => !p.ours)
  const hasSplit = firstOther > 0
  if (sorted.length === 0) return null
  return (
    <>
      <SectionTitle>当事人 · {sorted.length}</SectionTitle>
      <div className="px-6">
        {sorted.map((p, i) => (
          // 域模型无 id，用「姓名+角色」组合做 key：优于下标（排序后下标即身份会掩盖重排）
          <div key={`${p.name}|${p.role}`} className={'border-b border-border-light py-[7px] last:border-b-0 ' + (i === firstOther && hasSplit ? 'mt-3.5' : '')}>
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <span className={'text-[13px] font-semibold tracking-[-0.005em] ' + (p.ours ? '' : 'font-[600]')}>
                  {p.name}
                </span>
                <span className={'ml-2 text-[10.5px] text-muted-foreground ' + (p.ours ? 'text-foreground' : '')}>
                  {p.role || '当事人'}
                </span>
              </div>
              <CopyButton title="复制该当事人信息" getText={() => partyCopyText(p)} />
            </div>
            {(p.legalRep || p.idno || p.phone || p.address) && (
              <div className="mt-px text-[11px] leading-[1.55] break-all text-muted-foreground">
                {p.legalRep && <span className="mr-3 whitespace-nowrap">法定代表人 {p.legalRep}</span>}
                {p.idno && <span className="mr-3 whitespace-nowrap tabular-nums">{p.idno}</span>}
                {p.phone && <span className="mr-3 whitespace-nowrap tabular-nums">{p.phone}</span>}
                {p.address && <span>{p.address}</span>}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  )
}

export function TeamSection({ deal }: { deal: WorkbenchDeal }) {
  if (deal.team.length === 0) return null
  return (
    <>
      <SectionTitle>主办律师</SectionTitle>
      <div className="px-6">
        {deal.team.map((t) => {
          const tel = t.phone || (t.primary ? deal.primaryPhone : '')
          const firm = t.firm || (t.primary ? deal.lawFirm : '')
          return (
            <div key={`${t.name}|${t.license || t.phone}`} className="border-b border-border-light py-[9px] last:border-b-0">
              <div className="flex items-baseline gap-[9px]">
                <b className="text-[13px] font-[620]">{t.name}</b>
                {t.primary && (
                  <span className="flex-none rounded-[5px] border border-border px-[5px] text-[10px] text-muted-foreground">
                    主办
                  </span>
                )}
                {tel && <span className="flex-none text-[11.5px] text-muted-foreground tabular-nums">{tel}</span>}
                <div className="ml-auto self-center">
                  <CopyButton title="复制该律师信息" getText={() => lawyerCopyText(t, deal)} />
                </div>
              </div>
              {(t.license || firm) && (
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {t.license && <span className="mr-3.5">执业证号 <span className="tabular-nums">{t.license}</span></span>}
                  {firm && <span>{firm}</span>}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </>
  )
}

export function FactsSection({ deal }: { deal: WorkbenchDeal }) {
  const facts = dealFacts(deal)
  if (facts.length === 0) return null
  return (
    <>
      <SectionTitle>合同要素</SectionTitle>
      <div className="grid grid-cols-2 gap-x-[26px] px-6">
        {facts.map(([k, v]) => (
          <MetaRow key={k} k={k} v={v} />
        ))}
        {deal.customTerms && (
          <div className="col-span-full flex flex-col gap-[3px] border-b border-border-light py-[5px] text-xs last:border-b-0">
            <span className="text-[11px] text-muted-foreground">自定义收费条款</span>
            <span className="leading-[1.7] text-secondary-foreground">{deal.customTerms}</span>
          </div>
        )}
      </div>
    </>
  )
}

export function PaymentsSection({ deal }: { deal: WorkbenchDeal }) {
  const payRows = dealPayRows(deal)
  if (payRows.length === 0) return null
  return (
    <>
      <SectionTitle>收款记录</SectionTitle>
      <div className="px-6">
        {payRows.map((p) => (
          <div key={`${p.when}|${p.money}|${p.note}`} className="flex items-baseline gap-2.5 border-b border-border-light py-1.5 text-xs last:border-b-0">
            <span className="tabular-nums">{p.when}</span>
            <span className="font-[560] tabular-nums">{p.money}</span>
            <span className="ml-auto flex-none text-[11px] text-muted-foreground">{p.note}</span>
          </div>
        ))}
      </div>
    </>
  )
}

export function RemindersSection({ deal }: { deal: WorkbenchDeal }) {
  if (deal.work.length === 0) return null
  return (
    <>
      <SectionTitle>提醒事项 · {deal.work.length}</SectionTitle>
      <div className="px-6">
        {deal.work.map((w) => (
          <div key={`${w.t}|${w.dueFull}`} className="flex items-baseline gap-2.5 border-b border-border-light py-1.5 text-xs last:border-b-0">
            <span>{w.t}</span>
            <span className="ml-auto flex-none text-[11px] text-muted-foreground tabular-nums">
              {w.type ? w.type + ' · ' : ''}
              {w.dueFull}
            </span>
          </div>
        ))}
      </div>
    </>
  )
}

export function SupplementsSection({ deal }: { deal: WorkbenchDeal }) {
  if (deal.supps.length === 0) return null
  return (
    <>
      <SectionTitle>补充协议 · {deal.supps.length}</SectionTitle>
      <div className="px-6">
        {deal.supps.map((s) => (
          <div key={s.id} className="border-b border-border-light py-2.5 last:border-b-0">
            <div className="text-xs font-[560] text-secondary-foreground">{s.name}</div>
            <div className="mt-px text-[11px] text-muted-foreground tabular-nums">
              {fmtCNDate(s.created_at)}
              {s.parties.length ? ' · ' + s.parties.length + ' 方当事人' : ''}
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

export function CasesSection({
  deal,
  cases,
  isLoading,
  error,
  onRetry,
}: {
  deal: WorkbenchDeal
  cases: DealCase[]
  /** 案件明细还在路上：标题计数写「…」，正文给加载态 */
  isLoading: boolean
  /** 拉取失败的可读文案（null = 未失败）：失败要明说，空节会被读成「这份合同没有案件」 */
  error: string | null
  onRetry: () => void
}) {
  const stages = aggregateStages(cases)
  if (!error && !isLoading && stages.length === 0) return null
  return (
    <>
      <SectionTitle>案件 · {isLoading ? '…' : (deal.caseCount || cases.length)}</SectionTitle>
      <div className="px-6">
        {error ? (
          /* 失败要明说：空案件节会被律师读成「这份合同没有案件」 */
          <div className="py-2 text-xs text-destructive">
            {error} ·{' '}
            <button type="button" className="cursor-pointer underline underline-offset-3" onClick={onRetry}>
              重试
            </button>
          </div>
        ) : isLoading ? (
          <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            正在加载案件…
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-y-2 py-1.5">
              {stages.map((s, i) => (
                <StageNode key={s.stage} stage={s.stage} n={s.n} live={s.live} first={i === 0} />
              ))}
            </div>
            <div className="mt-0.5 text-[10.5px] text-muted-foreground/70">
              {cases.length} 个案件 · {stages.map((s) => s.stage).join(' → ')}
            </div>
          </>
        )}
      </div>
    </>
  )
}
