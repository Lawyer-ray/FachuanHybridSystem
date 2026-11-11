import { useState } from 'react'
import { FileText, Gavel } from 'lucide-react'

import { ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { StatusBadge } from '@/components/shared/status-badge'

import { CaseListPage } from './CaseListPage'
import { fmtMoney } from '../utils'
import { CourtFilingPanel } from './FilingPanels'
import { DocConvertPanel } from './DocConvertPanel'
import { OAStampPanel } from './OAActionPanels'
import { OAArchivePanel } from './ArchiveChecklistPanel'
import { ContractPanel } from './stages/ContractPanel'
import { FilingPanel } from './stages/FilingPanel'
import { GapPanel } from './stages/GapPanel'
import { IntakePanel } from './stages/IntakePanel'
import { ReturnedPanel } from './stages/ReturnedPanel'
import { UnderstandPanel } from './stages/UnderstandPanel'
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

type Section =
  | 'intake'      // ① 收案：客户发材料 → 自动拆分
  | 'understand'  // ② 读懂：自动转 markdown
  | 'gap'         // ③ 缺件：发现遗漏 → 通知客户
  | 'contract'    // ④ 文书：自动生成委托合同 → OA 利冲 → 立案
  | 'returned'    // ⑤ 回扫：邮箱/快递扫描件 → 自动归案
  | 'filing'      // ⑥ 校验：核签字盖章 → 通知律师去一张网
  | 'court'       // 一张网提交页（从 ⑥ 校验后进入）
  | 'convert'     // （保留）要素式转换
  | 'stamp'       // （保留）OA 盖章
  | 'archive'     // （保留）结案归档

/**
 * 分区顺序 = **律师办一个案子的真实时间线**，不是功能模块列表。
 *
 * 原先的七个分区（整包分段/起诉条件/要素式转换/OA立案/一张网/OA盖章/OA归档）
 * 是按「系统有哪些功能」排的，律师看不出先后关系，也看不出「一个案件在流动」。
 *
 * 现在按实际业务顺序重排：
 *   ① 收案  客户发来一堆材料 → 系统自动认、拆、命名
 *   ② 读懂  逐份转 markdown，给 AI 与律师都能读的正文
 *   ③ 缺件  发现遗漏 → 自动通知客户补什么
 *   ④ 文书  自动生成委托合同 → 派机器人去 OA 做利冲检索与立案
 *   ⑤ 回扫  客户寄回、行政扫描、邮箱自动扫到 → 自动归档到本案
 *   ⑥ 校验  核签字盖章 → 齐了才允许律师去一张网提交
 *   —— 后接要素式转换 / 盖章 / 归档（与上述主链并行的支线）
 */
const SECTIONS: { key: Section; label: string; icon: typeof Gavel; group: string; desc: string }[] = [
  { key: 'intake', label: '① 收案', icon: FileText, group: '主链 · 律师视角', desc: '客户材料自动拆分' },
  { key: 'understand', label: '② 读懂', icon: FileText, group: '主链 · 律师视角', desc: '逐份转 markdown' },
  { key: 'gap', label: '③ 缺件', icon: Gavel, group: '主链 · 律师视角', desc: '自动通知客户补件' },
  { key: 'contract', label: '④ 文书', icon: FileText, group: '主链 · 律师视角', desc: '委托合同 + OA 利冲立案' },
  { key: 'returned', label: '⑤ 回扫', icon: FileText, group: '主链 · 律师视角', desc: '寄回/扫描件自动归案' },
  { key: 'filing', label: '⑥ 校验', icon: Gavel, group: '主链 · 律师视角', desc: '核签字盖章 → 去一张网' },
  { key: 'court', label: '一张网提交', icon: Gavel, group: '主链 · 律师视角', desc: '校验通过后由律师点' },
  // 支线：主链之外的三件事，律师需要时才进
  { key: 'convert', label: '要素式转换', icon: FileText, group: '支线', desc: '传统起诉状→要素式' },
  { key: 'stamp', label: 'OA 盖章', icon: FileText, group: '支线', desc: '文件走盖章流程' },
  { key: 'archive', label: 'OA 归档', icon: FileText, group: '支线', desc: '结案材料入档' },
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
  const [section, setSection] = useState<Section>('intake')
  const c = useCase(caseId)

  if (c.loading) {
    return (
      <PageShell title="案件">
        <LoadingBlock text="正在加载案件…" />
      </PageShell>
    )
  }
  // 失败与「查无此案」是两件事，分开渲染：
  // 「加载失败」→ 可以重试（网络/5xx），文案交给 errMessage 抽后端原话；
  // 「案件不存在」→ 重试没有意义（404 / 已归档删除），给回退入口而不是重试按钮。
  // 此前两者挤在一个分支里用 `c.error ?? '案件不存在'` 兜底，导致 fallback 永不可达，
  // 且「查无此案」也挂着一个点了也没用的重试按钮。
  if (c.error) {
    return (
      <PageShell title="案件">
        <ErrorBlock error={c.error} fallback="案件加载失败" onRetry={c.reload} />
      </PageShell>
    )
  }
  if (!c.data) {
    return (
      <PageShell title="案件">
        <ErrorBlock error="案件不存在或已归档" fallback="案件不存在或已归档" onRetry={onBack} retryText="返回案件列表" />
      </PageShell>
    )
  }

  const k = c.data

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
        <nav className="sticky top-[76px] flex max-h-[calc(100vh-96px)] w-[168px] flex-none flex-col gap-2 overflow-y-auto pb-4">
          {groupedSections.map(([group, items]) => (
            <div key={group} className="flex flex-col gap-0.5">
              <div className="mb-1 px-2 text-[9.5px] font-semibold uppercase tracking-[.08em] text-faint">
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
                    aria-current={active ? 'page' : undefined}
                    className={
                      (active
                        ? 'bg-secondary font-medium text-foreground shadow-[inset_2px_0_0_0_var(--color-foreground)]'
                        : 'text-secondary-foreground hover:bg-secondary/60') +
                      ' flex items-start gap-2 rounded-[7px] px-2 py-[6px] text-left transition-colors'
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
        <div className="min-w-0 flex-1">
          {section === 'intake' ? <IntakePanel /> : null}
          {section === 'understand' ? <UnderstandPanel /> : null}
          {section === 'gap' ? <GapPanel /> : null}
          {section === 'contract' ? <ContractPanel /> : null}
          {section === 'returned' ? <ReturnedPanel /> : null}
          {section === 'filing' ? <FilingPanel /> : null}
          {section === 'court' ? <CourtFilingPanel caseId={caseId} /> : null}
          {section === 'convert' ? <DocConvertPanel caseId={caseId} /> : null}
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
    /* 容器口径与项目详情页（workbench/deal-detail）完全一致：
       mx-auto + 30px 边距 + 自 1400px 起的阶梯最大宽度。
       同一个案子从两个入口进来必须长一个样，否则律师会以为是两个系统。 */
    <main className="app-page-enter mx-auto max-w-[1280px] px-[30px] pt-[26px] pb-20 min-[1400px]:max-w-[1400px] min-[1900px]:max-w-[1760px] min-[2400px]:max-w-[2200px] max-[680px]:px-3 max-[680px]:pt-4 flex flex-col gap-[18px]">
      {/* 页头口径对齐项目详情页（workbench/DetailHeader）：
          面包屑 → 23px 大标题 → 单行 meta。
          原先这里是「返回箭头 + 17px 小标题」，和项目详情页完全两个样式，
          同一个案子从两个入口进来像两个系统。 */}
      <header>
        <nav className="mb-3.5 flex items-center gap-[7px] text-[12.5px] text-muted-foreground">
          <button
            type="button"
            onClick={onBack}
            className="transition-colors hover:text-foreground"
          >
            办案
          </button>
          <span>/</span>
          <span className="font-[550] text-foreground">立案工作台</span>
        </nav>

        <div className="mb-4 flex flex-wrap items-start gap-[18px]">
          <div className="min-w-0 flex-1">
            <h1
              className="text-[23px] leading-[1.4] font-[760] tracking-[-0.022em] break-all max-[680px]:text-[19px]"
              title={title}
            >
              {title}
            </h1>
            {meta ? (
              <div className="mt-1.5 text-[12px] text-muted-foreground">{meta}</div>
            ) : null}
          </div>
        </div>
      </header>
      {children}
    </main>
  )
}
