import { useCallback, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Navigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { LoadingBlock } from '@/components/shared/AsyncState'

import { DealDocLayout, type PickedFile } from './DealDocLayout'
import type { FolderEntryMutation } from './folder-tree-types'
import { useDocPreview } from './use-doc-preview'
import { DetailHeader } from './DetailHeader'
import { DetailRail } from './DetailRail'
import { ContractFileOverlays } from './ContractFileOverlays'
import { ServiceItemStream } from './ServiceItemStream'
import { PhaseListCard } from './PhaseListCard'
import { PhaseFoldersCard } from './PhaseFoldersCard'
import { AdvisorWorkbench, CrossBorderWorkbench, SpecialPhaseWorkbench } from './nonlit-workbench'
import { useServiceItems } from './use-service-items'
import { useSpecialPhases } from './use-special-phases'
import { listFolderEntries } from '../../api'
import { NonLitDetailDialogs } from './NonLitDetailDialogs'
import { NonLitTermBar } from './NonLitTermBar'
import { soonToast, useDealCopilotContext, useDealDetailPage } from './use-deal-detail-page'
import { refetchContractAndCases } from './refetch-contract'
import { usePhaseFileActions } from './use-phase-file-actions'
import { flattenTree } from './special-phase-tree'
import { Card, DetailError, RailSection } from './ui'

/**
 * 非诉工作台那一段的纵向栅格。
 *
 * 三个工作台组件返回的都是**一串 <Card> 兄弟节点**（Fragment 直接展开），
 * `DealDocLayout` 的 `space-y-[18px]` 只作用于「本层与相邻层」，管不到本层内部的
 * 兄弟卡——不在这里补栅格，卡就是贴死的（实测第 2 张 bottom === 第 3 张 top）。
 *
 * 用 `flex flex-col gap-[18px]` 而不是 `space-y-*`：本层内可能整段为空（无内容时
 * 返回 null），space-y 会给「第一个非空子元素」打 margin-top 依赖相邻选择器，
 * 有子元素条件渲染时容易算错；flex gap 只认实际参与布局的孩子，稳。
 */
const NONLIT_STACK = 'flex flex-col gap-[18px] mb-[18px]'

/**
 * 非诉项目详情页。
 *
 * 与争议解决详情页的差别只在**左栏**：诉讼是案件程序链，非诉是合同工作本身。
 *
 * **非诉内部还有两种工作脊椎**（54 号原型的结论：推进方式本质不同）：
 * - 常法顾问（caseType=advisor）：按「哪天做了什么」推进 → **服务事项流**
 * - 专项服务（caseType=special）：按合同约定的阶段交付 → **阶段与交付物表**
 *   阶段可设计（含层级与验收标准），交付物就地编辑，右栏目录名由阶段树派生。
 *
 * 判据是后端 case_type 代码值，不是页面里的猜测：阶段接口未上线时专项页仍给出
 * 「阶段与交付物」的空态（并告诉律师怎么建阶段），而不是默默退回流水视图。
 *
 * 右栏（期限 / 当事人 / 律师 / 收费 / 合同要素 / 文件夹）完全复用——那些都是合同
 * 层面的事实，与诉讼非诉无关。数据组装与助手上下文绑定在 use-deal-detail-page。
 */
export function NonLitDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { valid, d, deal, deadlines, contacts, money, next } = useDealDetailPage(id)
  const qc = useQueryClient()

  /** 用户手动指定的事项源目录（null = 自动识别「办案」） */
  const [manualSource, setManualSource] = useState<string | null>(null)
  /** 今天（yyyy-mm-dd）：服务期条与「今天」高亮共用，跨天刷新时只改这一处 */
  const todayStr = useMemo(() => {
    const n = new Date()
    return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')}`
  }, [])
  const [payOpen, setPayOpen] = useState(false)
  /** 新增期限弹窗（非诉没有案件卡，期限一律挂合同） */
  const [deadlineOpen, setDeadlineOpen] = useState(false)
  /** 新建下一程序案件（非诉项目通常没有阶段，只有数据漂移时才会出现这一行） */
  const [caseOpen, setCaseOpen] = useState(false)
  const onScheduleChanged = useCallback(() => {
    const id = deal?.id
    if (id == null) return
    refetchContractAndCases(qc, id)
    void qc.invalidateQueries({ queryKey: ['workbench', 'case-reminders', id] })
  }, [qc, deal?.id])
  const [invoiceOpen, setInvoiceOpen] = useState(false)
  /** 正在发起审查的文件（null = 抽屉关闭） */
  const [reviewTarget, setReviewTarget] = useState<{ subpath: string; name: string } | null>(null)
  /**
   * 非诉页的预览只有合同文件夹这一个来源，所以「是否同一份」只认 contract + 本项目 id
   * （诉讼页按选中文件的 kind/ownerId 比，见 use-doc-preview 的说明）。
   * 必须在 hook 之前定义：hook 会把它收进 onFolderMutated 的依赖里。
   */
  const contractFileStale = useCallback(
    (ev: FolderEntryMutation, _cur: PickedFile) => ev.kind === 'contract' && ev.ownerId === deal?.id,
    [deal?.id],
  )

  const {
    picked,
    setPicked,
    immersive,
    setImmersive,
    openPreview,
    closePreview,
    onFolderMutated,
    docSideBySide,
    doc,
  } = useDocPreview<PickedFile>({ isStale: contractFileStale })
  const markDirty = doc.markDirty

  const svc = useServiceItems('contract', deal?.id ?? null, { sourceSubpath: manualSource })
  const serviceItems = svc.items
  /**
   * 专项服务：阶段树 + 交付物（54 号原型脊椎）。两类非诉都调它（就是两次读请求），
   * 但只有专项页渲染——放在组件顶层是为了让分流不靠条件 Hook。
   */
  const special = useSpecialPhases('contract', deal?.id ?? null)
  const isSpecial = deal?.caseType === 'special'
  /**
   * 跨境合同审查（泰国工厂租赁）：项目名带「合同审查」的专项服务走跨境工作台。
   *
   * 判据只能是合同名——后端 case_type 只有 special / advisor 两个代码值，
   * 而跨境审查与关厂清盘在流程上不是一回事（前者是合同正文逐条审 + 外国法核验，
   * 后者是阶段与交付物）。没有这一层，泰国租赁项目会落到「设计阶段 / 校验交付物」卡上。
   */
  const isCrossBorder = isSpecial && (deal?.client ?? '').includes('合同审查')

  useDealCopilotContext(deal, '非诉项目详情')

  const tree = special.tree
  const { fileCountOf, draftIntoPhase, openFolderFromTree } = usePhaseFileActions({
    deal,
    tree,
    saveStages: special.saveStages,
    openPreview,
  })

  if (!valid) return <Navigate to="/projects" replace />
  if (d.isLoading) {
    // 占位高度与真容器同源：真内容里文档栏用的是 DealDocLayout.tsx:132 的
    // `h-[calc(100vh-100px)] min-h-[520px]`，这里取同一句的「一屏减页头」当最小
    // 高度，数据到手换页时纵向不跳（不新造高度魔法数）。
    return <LoadingBlock text="正在加载项目…" className="min-h-[calc(100vh-100px)]" />
  }
  if (d.error || !deal) {
    return <DetailError error={d.error ?? '项目不存在'} onRetry={() => d.refetch()} />
  }

  /** 右栏事实卡的完整入参（未预览 / 退到左栏底部两处都要用）；deal 由上一行守卫收窄为非空 */
  const railProps = {
    deadlines,
    today: d.today,
    contactGroups: contacts,
    team: deal.team,
    deal,
    moneyRows: money,
    onOpenFile: openPreview,
    onReviewFile: (f: { subpath: string; name: string }) => setReviewTarget(f),
    onAddDue: () => setDeadlineOpen(true),
    onAddPayment: () => setPayOpen(true),
    onOpenInvoices: () => setInvoiceOpen(true),
    // 发票关联/解除改了合同的开票金额：刷新合同（统计格、收款徽标、案件卡的钱）
    onMoneyChanged: () => refetchContractAndCases(qc, deal.id),
  }

  return (
    <main className="app-page-enter @container mx-auto max-w-[1280px] px-[30px] pt-[26px] pb-20 min-[1400px]:max-w-[1400px] min-[1900px]:max-w-[1760px] min-[2400px]:max-w-[2200px] min-[2600px]:max-w-[2480px] max-[680px]:px-3 max-[680px]:pt-4">
      <DetailHeader deal={deal} />

      {/* 周期轴：常法 → 服务期 + 事项刻度；专项 → 项目周期 + 阶段里程碑 */}
      <NonLitTermBar
        from={deal.from}
        to={deal.to}
        today={todayStr}
        isSpecial={isSpecial}
        tree={tree}
        serviceItems={serviceItems}
      />

      {/* 栅格三态（就地编辑）：① 左内容 + 右事实卡；② 净宽≥1100 时文档在右、事实卡退左栏底部；
          ③ 净宽不足时文档通栏、事实卡在其下。判定口径与实现见 DealDocLayout / use-net-width。 */}
      <DealDocLayout
        picked={picked}
        docSideBySide={docSideBySide}
        ownerId={deal.id}
        immersive={immersive}
        onToggleImmersive={() => setImmersive((v) => !v)}
        onClose={closePreview}
        onSaved={() => void d.refetch()}
        onReview={(f) => setReviewTarget(f)}
        onDirtyChange={markDirty}
        aside={
          isSpecial ? (
            <PhaseFoldersCard
              rows={flattenTree(tree).map((x) => ({ no: x.no, name: x.node.name, depth: x.depth }))}
              onOpenDir={(folder) => void openFolderFromTree(folder)}
            />
          ) : null
        }
        rail={
          <DetailRail
            {...railProps}
            showFolder={!isSpecial}
            folderSelectedSubpath={picked?.subpath ?? null}
            onFolderMutated={onFolderMutated}
          />
        }
      >
        {/* 非诉工作台：三个场景各配一组动作（与诉讼线六阶段交互同构）。
            包一层是因为三个工作台返回的都是一串 <Card>（Fragment 直接展开成一排兄弟），
            栅格由这一层统一给——**必须写在这里**：`DealDocLayout` 的 space-y 作用在本层
            与下层之间，管不到本层内部的兄弟卡，漏写就是「推进到下一阶段」与
            「推进前置校验」两张卡贴死（实测 bottom === top，零间距）。 */}
        <div className={NONLIT_STACK}>
          {isCrossBorder ? (
            <CrossBorderWorkbench />
          ) : isSpecial ? (
            <SpecialPhaseWorkbench />
          ) : deal.caseType === 'advisor' ? (
            <AdvisorWorkbench />
          ) : (
            <CrossBorderWorkbench />
          )}
        </div>

        {isSpecial ? (
          <PhaseListCard
            tree={tree}
            saving={special.saving}
            isLoading={special.isLoading}
            endpointNote={special.stagesError}
            fileCountOf={fileCountOf}
            onTreeChange={(next) => special.setTreeLocal(next)}
            onSave={(next) => void special.saveStages(next)}
            onOpenDeliverable={(deliverable) => {
              if (!deliverable.subpath) {
                toast.info('计划中的交付物还没有文件', { description: '先起草或把文件放进合同文件夹' })
                return
              }
              openPreview({
                subpath: deliverable.subpath,
                name: deliverable.subpath.split('/').pop() ?? deliverable.name,
              })
            }}
            onDraftInto={draftIntoPhase}
            note={deal.from && deal.to ? `项目周期 ${deal.from} 至 ${deal.to} 内按阶段验收的交付物` : '按阶段验收的交付物'}
          />
        ) : (
          <ServiceItemStream
            items={serviceItems}
            sourceSubpath={svc.sourceSubpath}
            candidates={svc.candidates}
            onChangeSource={setManualSource}
            isLoading={svc.isLoading}
            note={
              deal.from && deal.to
                ? `本服务期 ${deal.from} 至 ${deal.to} 内的服务事项与交付物`
                : '本服务期内的服务事项与交付物'
            }
            loadFiles={(subpath) => listFolderEntries('contract', deal.id, subpath).then((r) => r.files ?? [])}
            onOpenDeliverable={(f) => setPicked(f)}
            onAdd={() => soonToast('记服务事项')}
          />
        )}

        {next && (
          <Card>
            <RailSection title="下一程序">
              <div className="text-[12.5px] leading-[1.7] text-muted-foreground">
                合同已勾选的下一程序：<b className="font-[620] text-foreground">{next}</b>
                <button
                  type="button"
                  className="ml-3 cursor-pointer underline underline-offset-3 transition-colors hover:text-foreground"
                  onClick={() => setCaseOpen(true)}
                >
                  新建{next}
                </button>
              </div>
            </RailSection>
          </Card>
        )}
      </DealDocLayout>

      <ContractFileOverlays
        ownerId={deal.id}
        client={deal.parties?.client}
        reviewTarget={reviewTarget}
        onReviewClose={() => setReviewTarget(null)}
      />

      <NonLitDetailDialogs
        deal={deal}
        next={next}
        payOpen={payOpen}
        onPayClose={() => setPayOpen(false)}
        onPaymentSaved={() => void d.refetch()}
        invoiceOpen={invoiceOpen}
        onInvoiceClose={() => setInvoiceOpen(false)}
        caseOpen={caseOpen}
        onCaseClose={() => setCaseOpen(false)}
        onCaseSaved={() => refetchContractAndCases(qc, deal.id)}
        deadlineOpen={deadlineOpen}
        onDeadlineClose={() => setDeadlineOpen(false)}
        onScheduleSaved={onScheduleChanged}
        doc={doc}
      />
    </main>
  )
}
