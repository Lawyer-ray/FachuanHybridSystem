import { useState } from 'react'
import { ArrowLeft, FileText, Gavel } from 'lucide-react'

import { ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { StatusBadge } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'

import { CaseListPage } from './CaseListPage'
import { fmtMoney } from '../utils'
import { CourtFilingPanel, OAFilingPanel } from './FilingPanels'
import { ReadinessPanel } from './ReadinessPanel'
import { BundleSplitPanel } from './BundleSplitPanel'
import { DocConvertPanel } from './DocConvertPanel'
import { OAArchivePanel, OAStampPanel } from './OAActionPanels'
import { useCase } from '../hooks/use-cases'

/**
 * 银行批量诉讼 · 场景 2 全流程页。
 *
 * ═══ 为什么是一个页面而不是四个路由 ═══
 * 这条链路的四步（准备 → 要素式转换 → OA 立案 → 一张网）是**同一件事的连续动作**，
 * 每步之间来回跳会让律师丢失「我办到哪了」。做成一个页面内的分区，
 * 左边导航 + 右边内容，滚动位置与选中案件都保持。
 *
 * 拆路由的代价在原型阶段已经验证过：四个页面各存一份案件 id，
 * 从 A 案跳到 B 案时另外三个页面还停在 A，非常容易填错案。
 */

type Section = 'bundle' | 'readiness' | 'convert' | 'oa' | 'court' | 'stamp' | 'archive'

/**
 * 分区顺序 = 场景 2 的实际推进顺序：
 *   能不能立（起诉条件）→ 文书怎么来（要素式转换）→ 在律所 OA 立卷
 *   → 在法院系统立案 → 材料盖章 → 结案归档
 * 不按「功能模块」排，按「律师下一步该做什么」排。
 */
const SECTIONS: { key: Section; label: string; icon: typeof Gavel }[] = [
  // 整包分段是**真正的第一步**：律师拿到的是整包扫描件，
  // 拆不开就没有材料，后面所有校验都无从谈起。
  { key: 'bundle', label: '整包分段', icon: FileText },
  { key: 'readiness', label: '起诉条件', icon: Gavel },
  { key: 'convert', label: '要素式转换', icon: FileText },
  { key: 'oa', label: 'OA 立案', icon: FileText },
  { key: 'court', label: '一张网立案', icon: FileText },
  { key: 'stamp', label: 'OA 盖章', icon: FileText },
  { key: 'archive', label: 'OA 归档', icon: FileText },
]

export function BankLitigationPage({ initialCaseId }: { initialCaseId?: number | null } = {}) {
  const [caseId, setCaseId] = useState<number | null>(initialCaseId ?? null)

  if (caseId == null) {
    return (
      <PageShell title="银行批量诉讼">
        <CaseListPage onOpen={setCaseId} />
      </PageShell>
    )
  }
  return (
    <CaseWorkspace caseId={caseId} onBack={() => setCaseId(null)} />
  )
}

// ───────────────────────── 案件工作区 ─────────────────────────

function CaseWorkspace({ caseId, onBack }: { caseId: number; onBack: () => void }) {
  // 默认落在「整包分段」：这是律师打开案件后的第一个动作。
  const [section, setSection] = useState<Section>('bundle')
  const c = useCase(caseId)

  if (c.loading) {
    return (
      <PageShell title="案件">
        <LoadingBlock text="正在加载案件…" />
      </PageShell>
    )
  }
  if (c.error || !c.data) {
    return (
      <PageShell title="案件">
        <ErrorBlock error={c.error ?? '案件不存在'} fallback="案件加载失败" onRetry={c.reload} />
      </PageShell>
    )
  }

  const k = c.data
  const contractId = k.contract_id ?? null

  return (
    <PageShell
      title={k.name}
      onBack={onBack}
      meta={
        <>
          <span>{k.cause_of_action || '（未填案由）'}</span>
          <span className="text-border">·</span>
          <span>{k.current_stage || '（未设阶段）'}</span>
          <span className="text-border">·</span>
          <StatusBadge tone="blue" size="xs">
            {k.status}
          </StatusBadge>
          {k.target_amount ? (
            <>
              <span className="text-border">·</span>
              <span className="tabular-nums">标的 ¥{fmtMoney(k.target_amount)}</span>
            </>
          ) : null}
          {k.filing_number ? (
            <>
              <span className="text-border">·</span>
              <span className="truncate">{k.filing_number}</span>
            </>
          ) : null}
        </>
      }
    >
      <div className="flex gap-5">
        {/* 左侧分区导航 */}
        <nav className="flex w-[132px] flex-none flex-col gap-0.5">
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => setSection(s.key)}
              className={
                section === s.key
                  ? 'rounded-[7px] bg-secondary px-2.5 py-1.5 text-left text-[12.5px] font-medium text-foreground'
                  : 'rounded-[7px] px-2.5 py-1.5 text-left text-[12.5px] text-secondary-foreground transition-colors hover:bg-secondary/60'
              }
            >
              {s.label}
            </button>
          ))}
        </nav>

        {/* 右侧内容 */}
        <div className="min-w-0 flex-1">
          {section === 'bundle' ? <BundleSplitPanel caseId={caseId} stage={k.current_stage} /> : null}
          {section === 'readiness' ? <ReadinessPanel caseId={caseId} /> : null}
          {section === 'convert' ? <DocConvertPanel caseId={caseId} /> : null}
          {section === 'oa' ? <OAFilingPanel caseId={caseId} contractId={contractId} /> : null}
          {section === 'court' ? <CourtFilingPanel caseId={caseId} /> : null}
          {section === 'stamp' ? <OAStampPanel /> : null}
          {section === 'archive' ? <OAArchivePanel /> : null}
        </div>
      </div>
    </PageShell>
  )
}

// ───────────────────────── 页壳 ─────────────────────────

function PageShell({
  title,
  meta,
  onBack,
  children,
}: {
  title: string
  meta?: React.ReactNode
  onBack?: () => void
  children: React.ReactNode
}) {
  return (
    <main className="app-page-enter flex flex-col gap-4 px-7 pt-6 pb-16">
      <header className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          {onBack ? (
            <Button variant="ghost" size="icon-xs" onClick={onBack} aria-label="返回案件列表">
              <ArrowLeft className="size-3.5" />
            </Button>
          ) : null}
          <h1 className="min-w-0 truncate text-[17px] font-semibold leading-tight" title={title}>
            {title}
          </h1>
        </div>
        {meta ? (
          <div className="flex flex-wrap items-center gap-1.5 pl-[30px] text-[11.5px] text-muted-foreground">
            {meta}
          </div>
        ) : null}
      </header>
      {children}
    </main>
  )
}
