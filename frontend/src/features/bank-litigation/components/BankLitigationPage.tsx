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
const SECTIONS: { key: Section; label: string; icon: typeof Gavel; group: string; desc: string }[] = [
  // 整包分段是**真正的第一步**：律师拿到的是整包扫描件，
  // 拆不开就没有材料，后面所有校验都无从谈起。
  { key: 'bundle', label: '整包分段', icon: FileText, group: '立案前', desc: '拆包·复核·归案' },
  { key: 'readiness', label: '起诉条件', icon: Gavel, group: '立案前', desc: '主体·管辖·时效·材料' },
  { key: 'convert', label: '要素式转换', icon: FileText, group: '立案前', desc: '传统起诉状→要素式' },
  // 两个外部系统的立案动作。分组的意义：让律师知道「这两步离开法穿了」。
  { key: 'oa', label: 'OA 立案', icon: FileText, group: '外部系统', desc: '律所 OA 建卷' },
  { key: 'court', label: '一张网立案', icon: FileText, group: '外部系统', desc: '法院平台递交' },
  { key: 'stamp', label: 'OA 盖章', icon: FileText, group: '结案后', desc: '文件走盖章流程' },
  { key: 'archive', label: 'OA 归档', icon: FileText, group: '结案后', desc: '结案材料入档' },
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

  /* 导航分组：SECTIONS 自带 group，这里按首次出现顺序聚合成 [组名, 条目[]] */
  const groupedSections: [string, typeof SECTIONS][] = []
  for (const s of SECTIONS) {
    const last = groupedSections[groupedSections.length - 1]
    if (last && last[0] === s.group) last[1].push(s)
    else groupedSections.push([s.group, [s]])
  }

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
      <div className="flex gap-6">
        {/* 左栏分区导航（按「立案前 / 外部系统 / 结案后」分组）。
           宽度 176px + 每一项带副标题：原先只有 7 个裸文字，律师看不出
«立案前»和«结案后»是两段完全不同的工作，也不知道点进去会看到什么。
           whitespace-nowrap 保留：宁可横向溢出，不要在导航里断行。 */}
        <nav className="flex w-[176px] flex-none flex-col gap-3">
          {groupedSections.map(([group, items]) => (
            <div key={group} className="flex flex-col gap-0.5">
              <div className="mb-0.5 px-2 text-[10px] font-medium tracking-[.06em] text-faint">
                {group}
              </div>
              {items.map((s) => {
                const active = section === s.key
                const Icon = s.icon
                return (
                  <button
                    key={s.key}
                    type="button"
                    onClick={() => setSection(s.key)}
                    title={s.desc}
                    className={
                      (active
                        ? 'bg-secondary text-foreground'
                        : 'text-secondary-foreground hover:bg-secondary/60') +
                      ' flex items-start gap-2 rounded-[7px] px-2 py-[7px] text-left transition-colors'
                    }
                  >
                    <Icon
                      className={
                        (active ? 'text-foreground' : 'text-muted-foreground') +
                        ' mt-[1px] size-3.5 flex-none'
                      }
                    />
                    <span className="min-w-0">
                      <span className="block whitespace-nowrap text-[12.5px] font-medium leading-tight">
                        {s.label}
                      </span>
                      <span className="mt-0.5 block truncate text-[10px] leading-tight text-muted-foreground">
                        {s.desc}
                      </span>
                    </span>
                  </button>
                )
              })}
            </div>
          ))}
        </nav>

        {/* 右侧内容：封顶 1100px 并居中偏左。
           原先内容区在 1920px 屏上是 1696px 宽，而表单内容只有两三百字，
          右半边全空——这是「看起来像没做完」的主因。 */}
        <div className="min-w-0 max-w-[1100px] flex-1">
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
