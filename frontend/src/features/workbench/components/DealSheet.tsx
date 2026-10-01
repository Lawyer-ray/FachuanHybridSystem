import { Copy } from 'lucide-react'
import { toast } from 'sonner'

import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { copyTextToClipboard, fmtMoney, lawyerCopyText, partyCopyText, relDue } from '../domain'
import type { WorkbenchDeal } from '../types'

interface DealSheetProps {
  deal: WorkbenchDeal | null
  onOpenChange: (open: boolean) => void
}

/** 行内复制按钮：点击复制并 toast */
function CopyButton({ title, getText }: { title: string; getText: () => string }) {
  return (
    <button
      type="button"
      title={title}
      className="mt-0.5 flex size-6 flex-none items-center justify-center rounded-[7px] text-muted-foreground/50 opacity-60 transition-all hover:bg-foreground hover:text-background hover:opacity-100"
      onClick={(e) => {
        e.stopPropagation()
        const text = getText()
        void copyTextToClipboard(text).then(() => {
          toast.success('已复制：' + (text.split('\n')[0]?.replace(/（.*?）/, '').trim() ?? ''))
        })
      }}
    >
      <Copy className="size-3" />
    </button>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-6 pt-4 pb-2 text-[11px] font-[650] tracking-[0.09em] text-muted-foreground uppercase">
      {children}
    </div>
  )
}

function MetaRow({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border-light py-[5px] text-xs last:border-b-0">
      <span className="flex-none text-[11px] text-muted-foreground">{k}</span>
      <span className="min-w-0 text-right font-[560] break-all tabular-nums">{v}</span>
    </div>
  )
}

function MoneyCell({ label, value, hot }: { label: string; value: string; hot?: boolean }) {
  return (
    <div className="min-w-0 rounded-[11px] bg-secondary px-[11px] pt-2 pb-[7px]">
      <div className="text-[10.5px] whitespace-nowrap text-muted-foreground">{label}</div>
      <div className={'mt-px text-[15px] font-bold tracking-[-0.01em] truncate tabular-nums ' + (hot ? 'text-status-red' : '')}>
        {value}
      </div>
    </div>
  )
}

/** 程序节点：实心点=已结、空心粗环=在办，同阶段聚合 ×N */
function StageNode({ stage, n, live, first }: { stage: string; n: number; live: boolean; first: boolean }) {
  return (
    <div className="flex flex-none items-center gap-[7px]">
      {!first && <span className={'mx-[7px] h-0.5 w-6 flex-none rounded-sm ' + (live ? 'bg-border' : 'bg-foreground')} />}
      <span
        className={
          'size-[11px] flex-none rounded-full border-2 ' +
          (live ? 'border-foreground bg-card shadow-[0_0_0_3px_rgba(24,24,27,0.09)]' : 'border-foreground bg-foreground')
        }
      />
      <b className="text-xs font-[620]">{stage}</b>
      {n > 1 && <span className="-ml-1 text-[10px] font-semibold text-muted-foreground/70 tabular-nums">×{n}</span>}
      <span className={'text-[10.5px] ' + (live ? 'font-semibold text-foreground' : 'text-muted-foreground')}>
        {live ? '在办' : '已结'}
      </span>
    </div>
  )
}

/**
 * 合同详情抽屉（办案主页唯一浮层）：九节全字段，空节不渲染。
 * 「详情 →」= 开发中提示；当事人/律师行内可复制。
 */
export function DealSheet({ deal, onOpenChange }: DealSheetProps) {
  if (!deal) return null

  /* 当事人：我方在前，首个对方行上方留白断组（分组不用标签，角色已表达语义） */
  const sorted = [...deal.partiesAll].sort((a, b) => Number(b.ours) - Number(a.ours))
  const firstOther = sorted.findIndex((p) => !p.ours)
  const hasSplit = firstOther > 0

  const timeline: string[] = []
  if (deal.specified) timeline.push('指定 ' + deal.specified)
  if (deal.from) timeline.push('签订 ' + deal.from)
  if (deal.to) timeline.push('到期 ' + deal.to + (relDue(deal.daysLeft) ? '（' + relDue(deal.daysLeft) + '）' : ''))

  const facts = ([
    ['收费方式', deal.fee],
    ['风险比例', deal.riskRate != null ? deal.riskRate + '%' : ''],
    ['指定日期', deal.specified],
    ['签订日期', deal.from],
    ['到期日期', deal.to ? deal.to + (relDue(deal.daysLeft) ? '（' + relDue(deal.daysLeft) + '）' : '') : ''],
    ['代理阶段', deal.stages.join(' · ')],
    ['归档状态', deal.isFiled ? '已归档' : deal.statusLabel],
    ['建档编号', deal.filingNo],
    ['OA 编号', deal.no],
  ] as Array<[string, string]>).filter(([, v]) => !!v)

  const hasMoney = deal.amount || deal.totalReceived || deal.totalInvoiced || deal.unpaid
  const payRows = [
    ...deal.payments.map((p) => ({
      when: p.received_at || '',
      money: fmtMoney(p.amount) ?? '¥0',
      note: (p.invoice_status_label || '') + (p.note ? ' · ' + p.note : ''),
    })),
    ...deal.payRecords.map((p) => ({
      when: (p.created_at || '').slice(0, 10),
      money: fmtMoney(p.amount) ?? '¥0',
      note: '客户付款记录' + (p.note ? ' · ' + p.note : ''),
    })),
  ]

  /* 案件按阶段聚合（保持案件 id 升序的阶段顺序） */
  const seqCases = [...deal.cases].sort((a, b) => a.id - b.id)
  const stages: Array<{ stage: string; n: number; live: boolean }> = []
  for (const c of seqCases) {
    const last = stages[stages.length - 1]
    if (last && last.stage === c.proc) {
      last.n++
      last.live = last.live || !c.done
    } else {
      stages.push({ stage: c.proc, n: 1, live: !c.done })
    }
  }

  return (
    <Sheet open={!!deal} onOpenChange={onOpenChange}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>{deal.client}</SheetTitle>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11.5px] text-muted-foreground">
            <span className="rounded-full bg-secondary px-[9px] py-0.5 text-[10.5px] font-[550] text-secondary-foreground">
              {deal.ctype}
            </span>
            <span className="rounded-full bg-secondary px-[9px] py-0.5 text-[10.5px] font-[550] text-secondary-foreground">
              {deal.statusLabel}
            </span>
            {deal.no &&
              (deal.oaUrl ? (
                <a
                  href={deal.oaUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="underline underline-offset-3 tabular-nums hover:text-foreground"
                >
                  {deal.no}
                </a>
              ) : (
                <span className="tabular-nums">{deal.no}</span>
              ))}
            {timeline.length > 0 && <span className="tabular-nums">{timeline.join(' · ')}</span>}
          </div>
          <button
            type="button"
            className="absolute top-4 right-[54px] h-[30px] rounded-[9px] bg-foreground px-[13px] text-xs font-semibold text-background transition-opacity hover:opacity-85"
            onClick={() => toast.info('详情页正在开发中')}
          >
            详情 →
          </button>
        </SheetHeader>

        <SheetBody>
          {hasMoney && (
            <div className="grid grid-cols-4 gap-1.5 px-6 pt-4">
              <MoneyCell label="合同额" value={deal.amount ?? '—'} />
              <MoneyCell label="已收款" value={deal.totalReceived ?? '—'} />
              <MoneyCell label="已开票" value={deal.totalInvoiced ?? '—'} />
              <MoneyCell label="未收款" value={deal.unpaid ?? '—'} hot />
            </div>
          )}

          {sorted.length > 0 && (
            <>
              <SectionTitle>当事人 · {sorted.length}</SectionTitle>
              <div className="px-6">
                {sorted.map((p, i) => (
                  <div key={i} className={'border-b border-border-light py-[7px] last:border-b-0 ' + (i === firstOther && hasSplit ? 'mt-3.5' : '')}>
                    <div className="flex items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <span className={'text-[13px] font-semibold tracking-[-0.005em] ' + (p.ours ? '' : 'font-[600]')}>
                          {p.name}
                        </span>
                        <span className={'ml-2 text-[10.5px] text-muted-foreground ' + (p.ours ? 'text-foreground' : '')}>
                          {p.role || '当事人'}
                          {p.type ? ' · ' + p.type : ''}
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
          )}

          {deal.team.length > 0 && (
            <>
              <SectionTitle>主办律师</SectionTitle>
              <div className="px-6">
                {deal.team.map((t, i) => {
                  const tel = t.phone || (t.primary ? deal.primaryPhone : '')
                  const firm = t.firm || (t.primary ? deal.lawFirm : '')
                  return (
                    <div key={i} className="border-b border-border-light py-[9px] last:border-b-0">
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
          )}

          {facts.length > 0 && (
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
          )}

          {payRows.length > 0 && (
            <>
              <SectionTitle>收款记录</SectionTitle>
              <div className="px-6">
                {payRows.map((p, i) => (
                  <div key={i} className="flex items-baseline gap-2.5 border-b border-border-light py-1.5 text-xs last:border-b-0">
                    <span className="tabular-nums">{p.when}</span>
                    <span className="font-[560] tabular-nums">{p.money}</span>
                    <span className="ml-auto flex-none text-[11px] text-muted-foreground">{p.note}</span>
                  </div>
                ))}
              </div>
            </>
          )}

          {deal.work.length > 0 && (
            <>
              <SectionTitle>提醒事项 · {deal.work.length}</SectionTitle>
              <div className="px-6">
                {deal.work.map((w, i) => (
                  <div key={i} className="flex items-baseline gap-2.5 border-b border-border-light py-1.5 text-xs last:border-b-0">
                    <span>{w.t}</span>
                    <span className="ml-auto flex-none text-[11px] text-muted-foreground tabular-nums">
                      {w.type ? w.type + ' · ' : ''}
                      {w.dueFull}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}

          {deal.supps.length > 0 && (
            <>
              <SectionTitle>补充协议 · {deal.supps.length}</SectionTitle>
              <div className="px-6">
                {deal.supps.map((s) => (
                  <div key={s.id} className="border-b border-border-light py-2.5 last:border-b-0">
                    <div className="text-xs font-[560] text-secondary-foreground">{s.name}</div>
                    <div className="mt-px text-[11px] text-muted-foreground tabular-nums">
                      {(s.created_at || '').slice(0, 10)}
                      {s.parties.length ? ' · ' + s.parties.length + ' 方当事人' : ''}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {stages.length > 0 && (
            <>
              <SectionTitle>案件 · {deal.cases.length}</SectionTitle>
              <div className="px-6">
                <div className="flex flex-wrap items-center gap-y-2 py-1.5">
                  {stages.map((s, i) => (
                    <StageNode key={s.stage} stage={s.stage} n={s.n} live={s.live} first={i === 0} />
                  ))}
                </div>
                <div className="mt-0.5 text-[10.5px] text-muted-foreground/70">
                  {deal.cases.length} 个案件 · {stages.map((s) => s.stage).join(' → ')} · 个案详情开发中
                </div>
              </div>
            </>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  )
}
