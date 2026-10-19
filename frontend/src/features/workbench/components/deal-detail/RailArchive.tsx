import { dealPayRows, fmtCNDate, partyCopyText } from '../../domain'
import { safeHttpUrl } from '@/lib/url'
import type { WorkbenchDeal } from '../../types'
import { CopyButton } from '../DealSheetParts'
import { railFacts, railParties } from './detail-domain'
import { KV, RailAction, RailSection } from './ui'

/**
 * 右栏里合同层面的档案节：当事人 / 收款 / 补充协议 / 合同要素。
 * 左列只放案件本身（程序链），合同的事全在右栏这张卡里；空节不渲染，收款例外（「＋ 记收款」要有落点）。
 */

export function RailParties({ deal }: { deal: WorkbenchDeal }) {
  const { rows, firstOther } = railParties(deal)
  if (rows.length === 0) return null
  return (
    <RailSection title={'当事人 · ' + rows.length}>
      {rows.map((p, i) => (
        <div
          key={p.name + '|' + p.role}
          // 我方在前，首个对方上方留白断组——分组靠留白，不加「对方当事人 · N」之类标签
          className={'border-b border-border-light py-[6px] last:border-b-0 ' + (i === firstOther && firstOther > 0 ? 'mt-3' : '')}
        >
          <div className="flex items-start gap-2">
            <span className="min-w-0 flex-1">
              <span className="text-[13px] font-[620] tracking-[-0.005em]">{p.name}</span>
              <span className={'ml-1.5 text-[10.5px] ' + (p.ours ? 'text-foreground' : 'text-muted-foreground')}>
                {p.role || '当事人'}
              </span>
            </span>
            <CopyButton title="复制该当事人信息" getText={() => partyCopyText(p)} />
          </div>
          {(p.legalRep || p.phone || p.idno || p.address) && (
            <div className="mt-px text-[11px] leading-[1.55] break-all text-muted-foreground tabular-nums">
              {p.legalRep && <span className="mr-2.5 whitespace-nowrap">法定代表人 {p.legalRep}</span>}
              {p.phone && <span className="mr-2.5 whitespace-nowrap">{p.phone}</span>}
              {p.idno && <span className="mr-2.5 whitespace-nowrap">{p.idno}</span>}
              {p.address && <span>{p.address}</span>}
            </div>
          )}
        </div>
      ))}
    </RailSection>
  )
}

export function RailPayments({ deal, onAdd }: { deal: WorkbenchDeal; onAdd: () => void }) {
  const rows = dealPayRows(deal)
  return (
    <RailSection
      title={rows.length ? '收款 · ' + rows.length + ' 笔' : '收款'}
      action={<RailAction onClick={onAdd}>＋ 记收款</RailAction>}
    >
      {rows.length === 0 ? (
        <div className="text-xs text-muted-foreground/70">还没有收款记录</div>
      ) : (
        rows.map((p) => (
          <div key={p.when + '|' + p.money + '|' + p.note} className="border-b border-border-light py-[6px] last:border-b-0">
            <div className="flex items-baseline gap-2 text-[13px]">
              <b className="font-[680] tabular-nums">{p.money}</b>
              <span className="ml-auto text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">{p.when}</span>
            </div>
            {p.note && <div className="mt-px text-[11px] text-muted-foreground">{p.note}</div>}
          </div>
        ))
      )}
    </RailSection>
  )
}

export function RailSupps({ deal }: { deal: WorkbenchDeal }) {
  if (deal.supps.length === 0) return null
  return (
    <RailSection title={'补充协议 · ' + deal.supps.length}>
      {deal.supps.map((s) => (
        <div key={s.id} className="border-b border-border-light py-[6px] last:border-b-0">
          <div className="text-[12.5px] font-[560] text-secondary-foreground">{s.name}</div>
          <div className="mt-px text-[11px] text-muted-foreground tabular-nums">
            {fmtCNDate(s.created_at)}
            {s.parties.length ? ' · ' + s.parties.length + ' 方当事人' : ''}
          </div>
        </div>
      ))}
    </RailSection>
  )
}

export function RailFacts({ deal }: { deal: WorkbenchDeal }) {
  const facts = railFacts(deal)
  if (facts.length === 0 && !deal.customTerms) return null
  return (
    <RailSection title="合同要素">
      {facts.map(([k, v]) => (
        // OA 编号：有律所 ID 对应的 OA 地址才可跳（与列表抽屉同一判定），否则纯文本
        <KV
          key={k}
          k={k}
          v={v}
          kw={56}
          href={k === 'OA 编号' && deal.oaUrl ? safeHttpUrl(deal.oaUrl, '#') : undefined}
        />
      ))}
      {deal.customTerms && <KV k="收费条款" v={deal.customTerms} kw={56} muted />}
    </RailSection>
  )
}
