import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { safeHttpUrl } from '@/lib/url'
import { aggregateStages, dealFacts, dealPayRows, fmtCNDate, lawyerCopyText, partyCopyText } from '../domain'
import { useContractCases } from '../hooks/use-contract-cases'
import type { WorkbenchDeal } from '../types'

import { CopyButton, MetaRow, MoneyCell, SectionTitle, StageNode } from './DealSheetParts'

interface DealSheetProps {
  deal: WorkbenchDeal | null
  /** 开关与 deal 分离：关闭时父组件保留最后一份 deal，让退出动画播完再由 Radix 卸载 */
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 「详情 →」去向：争议解决进详情页；不传（测试）退化为开发中提示 */
  onOpenDetail?: (deal: WorkbenchDeal) => void
}

/**
 * 合同详情抽屉（办案主页唯一浮层）：九节全字段，空节不渲染。
 * 「详情 →」= 详情页（争议解决）/ 开发中提示（非诉）；当事人/律师行内可复制。
 * 头部只放类型/状态/OA 编号——日期类信息统一在「合同要素」一节，不在头部重复。
 */
export function DealSheet({ deal, open, onOpenChange, onOpenDetail }: DealSheetProps) {
  /* 案件明细按需加载：抽屉打开才请求该合同的案件（列表期不拉全量） */
  const { cases, isLoading: casesLoading, error: casesError, refetch: refetchCases } = useContractCases(
    open ? (deal?.id ?? null) : null,
  )
  if (!deal) return null

  /* 右键空白遮罩 = 左键点空白同效：不弹原生菜单，收起抽屉（播退出动画） */
  const closeByContextMenu = (e: React.MouseEvent) => {
    e.preventDefault()
    onOpenChange(false)
  }

  /* 当事人：我方在前，首个对方行上方留白断组（分组不用标签，角色已表达语义） */
  const sorted = [...deal.partiesAll].sort((a, b) => Number(b.ours) - Number(a.ours))
  const firstOther = sorted.findIndex((p) => !p.ours)
  const hasSplit = firstOther > 0

  const facts = dealFacts(deal)
  const payRows = dealPayRows(deal)

  const hasMoney = deal.amount || deal.totalReceived || deal.totalInvoiced || deal.unpaid

  /* 案件按阶段聚合，数据来自按需加载 */
  const stages = aggregateStages(cases)

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent overlayProps={{ onContextMenu: closeByContextMenu }}>
        <SheetHeader>
          {/* 详情按钮右浮动进标题流：长案名首行文字自动绕开按钮，不再被盖住；
              flow-root 兜住浮动高度，下方标签行不会钻到按钮下面；mr 对齐右侧 X（54px） */}
          <div className="flow-root">
            <button
              type="button"
              className="-mt-1 float-right ml-3 mr-[30px] h-[30px] rounded-[9px] bg-foreground px-[13px] text-xs font-semibold text-background transition-opacity hover:opacity-85"
              onClick={() => (onOpenDetail && deal ? onOpenDetail(deal) : toast.info('详情页正在开发中'))}
            >
              详情 →
            </button>
            <SheetTitle>{deal.client}</SheetTitle>
          </div>
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
                  href={safeHttpUrl(deal.oaUrl, '#')}
                  target="_blank"
                  rel="noreferrer"
                  className="underline underline-offset-3 tabular-nums hover:text-foreground"
                >
                  {deal.no}
                </a>
              ) : (
                <span className="tabular-nums">{deal.no}</span>
              ))}
          </div>
        </SheetHeader>

        <SheetBody>
          {hasMoney && (
            <div className="grid grid-cols-4 gap-1.5 px-6 pt-4">
              <MoneyCell label="律师费" value={deal.amount ?? '—'} />
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
          )}

          {deal.team.length > 0 && (
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
                {payRows.map((p) => (
                  <div key={`${p.when}|${p.money}|${p.note}`} className="flex items-baseline gap-2.5 border-b border-border-light py-1.5 text-xs last:border-b-0">
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
          )}

          {deal.supps.length > 0 && (
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
          )}

          {(casesError || casesLoading || stages.length > 0) && (
            <>
              <SectionTitle>案件 · {casesLoading ? '…' : (deal.caseCount || cases.length)}</SectionTitle>
              <div className="px-6">
                {casesError ? (
                  /* 失败要明说：空案件节会被律师读成「这份合同没有案件」 */
                  <div className="py-2 text-xs text-destructive">
                    {casesError} ·{' '}
                    <button type="button" className="cursor-pointer underline underline-offset-3" onClick={() => refetchCases()}>
                      重试
                    </button>
                  </div>
                ) : casesLoading ? (
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
                      {!deal.lit && ' · 个案详情开发中'}
                    </div>
                  </>
                )}
              </div>
            </>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  )
}
