import type { ReactNode } from 'react'
import { toast } from 'sonner'

import { copyText } from '@/lib/clipboard'
import type { DealContact, DealTeamMember, WorkbenchDeal } from '../../types'
import type { Deadline } from './detail-domain'
import { dueLabel } from './detail-domain'
import { RailFacts, RailParties, RailPayments, RailSupps } from './RailArchive'
import { FolderTree } from './FolderTree'
import { Card, CopyText, KV, RailAction, RailSection } from './ui'

/**
 * 右栏合同卡：期限（未来预警，红色只给「今天」）· 当事人 · 法院联系人 · 律师 · 涉案与收费 ·
 * 收款 · 补充协议 · 合同要素。合同层面的信息全在这张卡里，左列只放案件程序链。
 * 不做 sticky：卡片常比视口高，钉住就得卡内滚动，收款/合同要素会被裁在看不见的地方；
 * 随页面流动才能一眼看全。
 */
export function DetailRail({
  deadlines,
  today,
  contactGroups,
  team,
  deal,
  moneyRows,
  onAddDue,
  onAddPayment,
  showFolder = true,
  onOpenFile,
  onReviewFile,
  folderPreview,
}: {
  deadlines: Deadline[]
  today: Date
  contactGroups: Array<{ group: string; rows: DealContact[] }>
  team: DealTeamMember[]
  deal: WorkbenchDeal
  moneyRows: Array<[string, string]>
  onAddDue: () => void
  onAddPayment: () => void
  /**
   * 是否渲染合同文件夹树。
   *
   * 非诉页传 false：那份文件夹是左栏的主角（独占整栏、可展开预览），
   * 右栏再画一棵同样的树就是同屏两份同样的内容，且 320px 高度下几乎没法用。
   * 诉讼页保持 true——左栏是案件程序链，文件夹作次要信息放右栏合适。
   */
  showFolder?: boolean
  /** 点文件夹里的文件 → 由本组件就地展开预览（诉讼页走这条路） */
  onOpenFile?: (f: { subpath: string; name: string; size?: number; modified_at?: string }) => void
  /** 「AI 审查」入口（仅 docx） */
  onReviewFile?: (f: { subpath: string; name: string }) => void
  /** 渲染在文件夹树上方的预览卡（由调用方给出，保持本组件不依赖 OnlyOffice） */
  folderPreview?: ReactNode
}) {
  const copy = (text: string) => {
    void copyText(text).then(() => toast.success('已复制'))
  }

  return (
    <Card>
      <RailSection
        title="期限"
        action={
          <RailAction onClick={onAddDue}>＋ 新增</RailAction>
        }
      >
        {deadlines.length === 0 ? (
          <div className="text-xs text-muted-foreground/70">暂无未来期限</div>
        ) : (
          deadlines.map((d) => (
            <div key={d.key} className="grid grid-cols-[14px_1fr] py-1.5">
              <span className="relative">
                <span
                  className={
                    'absolute top-[6px] rounded-full ' + (d.today ? 'left-[2.5px] size-[8px] bg-status-red' : 'left-[3px] size-[7px] bg-border')
                  }
                />
              </span>
              <span className="min-w-0 pl-[7px]">
                <span className={'block text-[12.5px] leading-[1.5] ' + (d.today ? 'font-[640] text-status-red' : 'text-secondary-foreground')}>
                  {d.typeLabel && (
                    <span className="mr-[5px] rounded-[5px] border border-border-light bg-secondary px-[5px] align-[-1px] text-[10px] font-[620] text-secondary-foreground">
                      {d.typeLabel}
                    </span>
                  )}
                  {d.content}
                </span>
                <span className="mt-px block text-[11px] whitespace-nowrap text-muted-foreground/80 tabular-nums">
                  {dueLabel(d.due, today)}
                  {d.today ? ' · 今天' : ''}
                  <b className="ml-2 font-[620] text-muted-foreground">{d.scope}</b>
                </span>
              </span>
            </div>
          ))
        )}
      </RailSection>

      <RailParties deal={deal} />

      {contactGroups.length > 0 && (
        <RailSection title="法院联系人">
          {contactGroups.map((g) => (
            <div key={g.group}>
              <div className="mt-2 mb-[3px] text-[11px] font-[650] text-muted-foreground/80 first:mt-0">{g.group}</div>
              {g.rows.map((r, i) => (
                <div key={r.name + i}>
                  <div className="flex items-baseline gap-2 py-[3.5px] text-[12.5px]">
                    <span className="font-semibold">{r.name}</span>
                    {r.role && <span className="text-[11px] text-muted-foreground">{r.role}</span>}
                    {r.phone && (
                      <span className="ml-auto flex items-baseline gap-1 whitespace-nowrap text-[12px] font-[560] text-secondary-foreground tabular-nums">
                        {r.phone}
                        <CopyText text={r.phone} onCopy={copy} />
                      </span>
                    )}
                  </div>
                  {r.address && <div className="pb-1 text-[11px] leading-[1.6] break-words text-muted-foreground/80">{r.address}</div>}
                </div>
              ))}
            </div>
          ))}
        </RailSection>
      )}

      {team.length > 0 && (
        <RailSection title="律师">
          {team.map((t) => (
            <div key={t.name + '|' + t.license} className="py-1">
              <div className="flex items-baseline gap-2 text-[13px]">
                <b className="font-[640]">{t.name}</b>
                {t.primary && (
                  <span className="rounded-[5px] border border-border bg-secondary px-[5px] text-[10.5px] font-[620] text-secondary-foreground">
                    主办
                  </span>
                )}
                {(t.phone || (t.primary && deal.primaryPhone)) && (
                  <span className="ml-auto flex items-baseline gap-1 text-[11.5px] text-muted-foreground tabular-nums">
                    {t.phone || deal.primaryPhone}
                    <CopyText text={t.phone || deal.primaryPhone} onCopy={copy} />
                  </span>
                )}
              </div>
              {t.license && (
                <div className="mt-px text-[11.5px] text-muted-foreground tabular-nums">执业证号 {t.license}</div>
              )}
              {t.firm && <div className="mt-px text-[11.5px] break-words text-muted-foreground">{t.firm}</div>}
            </div>
          ))}
        </RailSection>
      )}

      {moneyRows.length > 0 && (
        <RailSection title="涉案与收费">
          {moneyRows.map(([k, v]) => (
            <KV key={k} k={k} v={v} kw={56} />
          ))}
        </RailSection>
      )}

      <RailPayments deal={deal} onAdd={onAddPayment} />
      <RailSupps deal={deal} />

      {/* 合同文件夹：绑定目录的树形浏览；标题行自带「新建文件夹」，未绑定时树内提示。
          非诉页不渲染（那份树在左栏独占，见 NonLitDetailPage）。 */}
      {showFolder && (
        <div className="border-t border-border-light px-[18px] pt-3.5 pb-[15px]">
          {folderPreview}
          <FolderTree
            kind="contract"
            ownerId={deal.id}
            maxH="max-h-[320px]"
            title="合同文件夹"
            onOpenFile={onOpenFile}
            onReviewFile={onReviewFile}
          />
        </div>
      )}

      <RailFacts deal={deal} />
    </Card>
  )
}
