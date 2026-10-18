import { fmtCNDate, dealFacts, dealPayRows, partyCopyText } from '../../domain'
import type { WorkbenchDeal } from '../../types'
import { CopyButton } from '../DealSheetParts'
import { Card, CardHead, ActionButton, KV } from './ui'

/** 表格单元格基类：横线分隔 + 桌面/窄屏水平内边距（表头加字距，金额列右对齐在调用处补） */
const TH = 'border-b border-border-light px-5 py-2 text-[11px] font-semibold tracking-[0.03em] whitespace-nowrap text-muted-foreground/70 max-[680px]:px-3.5'
const TD = 'border-b border-border-light px-5 py-2 tabular-nums max-[680px]:px-3.5 transition-colors'

/**
 * 档案沉底：当事人全列 / 合同要素 / 收款 / 补充协议。列表页抽屉已能快览这些，
 * 这里给的是同样的字段但完整展开；空节不渲染。
 */
export function DetailArchive({ deal, onAddPayment }: { deal: WorkbenchDeal; onAddPayment: () => void }) {
  const sorted = [...deal.partiesAll].sort((a, b) => Number(b.ours) - Number(a.ours))
  const facts = dealFacts(deal)
  const payRows = dealPayRows(deal)

  return (
    <>
      {sorted.length > 0 && (
        <Card>
          <CardHead title="当事人" count={sorted.length} />
          <div className="pt-1">
            {sorted.map((p) => (
              <div key={p.name + '|' + p.role} className="flex items-center gap-3 border-t border-border-light px-5 py-2.5 first:border-t-0 max-[680px]:px-3.5">
                <span className="flex size-[38px] flex-none items-center justify-center rounded-[11px] border border-border bg-secondary text-sm font-bold text-secondary-foreground">
                  {p.name.slice(0, 1) || '?'}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-[620] tracking-[-0.01em]">{p.name}</span>
                  {(p.legalRep || p.phone || p.idno || p.address) && (
                    <span className="mt-px block text-[11.5px] leading-[1.55] break-all text-muted-foreground tabular-nums">
                      {p.legalRep && <span className="mr-3 whitespace-nowrap">法定代表人 {p.legalRep}</span>}
                      {p.phone && <span className="mr-3 whitespace-nowrap">{p.phone}</span>}
                      {p.idno && <span className="mr-3 whitespace-nowrap">{p.idno}</span>}
                      {p.address && <span>{p.address}</span>}
                    </span>
                  )}
                </span>
                <span className="rounded-[6px] border border-border bg-secondary px-2 py-px text-[11px] font-semibold whitespace-nowrap text-secondary-foreground">
                  {p.role || '当事人'}
                </span>
                <CopyButton title="复制该当事人信息" getText={() => partyCopyText(p)} />
              </div>
            ))}
          </div>
        </Card>
      )}

      {facts.length > 0 && (
        <Card>
          <CardHead title="合同要素" dim="档案" />
          <div className="grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-x-[26px] px-5 pt-1.5 pb-3.5 max-[680px]:grid-cols-1 max-[680px]:px-3.5">
            {facts.map(([k, v]) => (
              <KV key={k} k={k} v={v} />
            ))}
            {deal.customTerms && <KV k="收费条款" v={deal.customTerms} full muted />}
          </div>
        </Card>
      )}

      {payRows.length > 0 && (
        <Card>
          <CardHead
            title="收款"
            count={payRows.length + ' 笔'}
            action={
              <ActionButton sm onClick={onAddPayment}>
                ＋ 记收款
              </ActionButton>
            }
          />
          <table className="mt-1.5 w-full border-separate border-spacing-0 text-[13px] [&_tbody_tr:hover_td]:bg-secondary/40 [&_tr:last-child_td]:border-b-0">
            <thead>
              <tr>
                <th className={TH + ' text-left'}>收款日期</th>
                <th className={TH + ' text-left font-normal'}>摘要</th>
                <th className={TH + ' text-right'}>金额</th>
              </tr>
            </thead>
            <tbody>
              {payRows.map((p) => (
                <tr key={p.when + '|' + p.money + '|' + p.note}>
                  <td className={TD + ' whitespace-nowrap text-[12.5px] text-muted-foreground'}>{p.when}</td>
                  <td className={TD + ' text-[12.5px] text-muted-foreground'}>{p.note}</td>
                  <td className={TD + ' text-right font-[680]'}>{p.money}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {deal.supps.length > 0 && (
        <Card>
          <CardHead title="补充协议" count={deal.supps.length} />
          <table className="mt-1.5 w-full border-separate border-spacing-0 text-[13px] [&_tbody_tr:hover_td]:bg-secondary/40 [&_tr:last-child_td]:border-b-0">
            <tbody>
              {deal.supps.map((s) => (
                <tr key={s.id}>
                  <td className={TD + ' w-24 whitespace-nowrap text-[12.5px] text-muted-foreground'}>{fmtCNDate(s.created_at)}</td>
                  <td className={TD + ' font-semibold'}>{s.name}</td>
                  <td className={TD + ' text-right text-[12.5px] text-muted-foreground'}>
                    {s.parties.length ? s.parties.length + ' 方当事人' : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  )
}
