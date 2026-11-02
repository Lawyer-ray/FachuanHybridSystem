/**
 * 跨境审查（泰国工厂租赁）的文档视图组合
 *
 * `CrossBorderWorkbench` 负责「机器怎么跑」（动作卡 + 进度日志），这里负责
 * 「律师拿到什么、怎么用」：docx 原文（OnlyOffice）、双语对照正文、法条核验
 * 依据、可筛选的修订清单、逐条采纳。后四块共享同一个「当前选中的修订」，
 * 点清单会联动高亮正文与法条；原文卡是**真文件**，只看不改，不参与联动。
 */

import { useCallback, useState } from 'react'

import { DEMO_NL2_REVIEW_PROGRESS, DEMO_TH_CONTRACT_REVISIONS } from '../../demo-nonlit'
import { Card } from '../../ui'
import { BilingualContractCard } from './BilingualContractCard'
import { ContractOfficeCard } from './ContractOfficeCard'
import { LawGateCard } from './LawGateCard'
import { RevisionBoard } from './RevisionBoard'
import { RevisionWalkCard } from './RevisionWalkCard'

/** 审查会话进度：审了几条、还剩几条、用时 */
export function ReviewProgressCard() {
  const p = DEMO_NL2_REVIEW_PROGRESS
  const pct = Math.round((p.reviewed / p.total) * 100)
  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex flex-wrap items-baseline gap-2">
        <h3 className="text-[13px] font-[620]">审查进度</h3>
        <span className="text-[11px] text-muted-foreground">
          已审 {p.reviewed} / {p.total} 条 · 还剩 {p.remain} 条 · 用时 {p.elapsed}（预计再 {p.eta}）
        </span>
        <span className="ml-auto text-[10.5px] text-muted-foreground">审查人 {p.reviewer}</span>
      </div>
      <div className="mt-2.5 h-[6px] overflow-hidden rounded-full bg-secondary">
        <div className="h-full rounded-full bg-foreground transition-[width] duration-300" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10.5px] text-muted-foreground">
        <span>最近落笔：{p.lastClause}</span>
        <span>·</span>
        <span>进度 {pct}%</span>
        <span>·</span>
        <span>检出修订 {DEMO_TH_CONTRACT_REVISIONS.length} 处</span>
      </div>
    </Card>
  )
}

export function CrossBorderViews({ lawVerified }: { lawVerified: boolean }) {
  /** 当前选中的修订：清单展开、正文高亮、法条回查三处共用 */
  const [picked, setPicked] = useState<string | null>(null)
  const [tabId, setTabId] = useState('all')
  const [decided, setDecided] = useState<Record<string, 'accept' | 'reject'>>({})

  const pick = useCallback((id: string) => setPicked(id), [])

  return (
    <>
      <div className="mt-4">
        <ReviewProgressCard />
      </div>
      <div className="mt-4">
        <ContractOfficeCard />
      </div>
      <div className="mt-4">
        <BilingualContractCard focusRev={picked} onPickRev={pick} />
      </div>
      <div className="mt-4">
        <LawGateCard active={lawVerified} onPickRev={pick} />
      </div>
      <div className="mt-4">
        <RevisionBoard tabId={tabId} onPickTab={setTabId} picked={picked} onPick={setPicked} />
      </div>
      <div className="mt-4">
        <RevisionWalkCard
          decided={decided}
          onDecide={(id, verdict) => setDecided((v) => ({ ...v, [id]: verdict }))}
          onReset={() => setDecided({})}
          onPickRev={pick}
        />
      </div>
    </>
  )
}
