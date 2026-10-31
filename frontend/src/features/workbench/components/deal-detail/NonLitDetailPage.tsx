import { useCallback, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Navigate, useParams } from 'react-router'
import { Loader2 } from 'lucide-react'

import { toast } from 'sonner'

import { DealDocLayout, DOC_SIDE_BY_SIDE_MIN, type PickedFile } from './DealDocLayout'
import { DetailHeader } from './DetailHeader'
import { DetailRail } from './DetailRail'
import { ContractFileOverlays } from './ContractFileOverlays'
import { ServiceItemStream } from './ServiceItemStream'
import { PhaseListCard } from './PhaseListCard'
import { PhaseFoldersCard } from './PhaseFoldersCard'
import { useServiceItems } from './use-service-items'
import { useSpecialPhases } from './use-special-phases'
import { listFolderEntries } from '../../api'
import { TermBar } from './TermBar'
import { PaymentDialog } from './PaymentDialog'
import { InvoicePoolDialog } from './InvoicePoolDialog'
import { soonToast, useDealCopilotContext, useDealDetailPage } from './use-deal-detail-page'
import { refetchContractAndCases } from './refetch-contract'
import { addDeliverable } from './special-phase-crud'
import { flattenTree, patchPhase, type PhaseNode } from './special-phase-tree'
import { useDockedViewport, useNetWidth } from './use-net-width'
import { Card, DetailError, RailSection } from './ui'

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
  const [invoiceOpen, setInvoiceOpen] = useState(false)
  /** 正在发起审查的文件（null = 抽屉关闭） */
  const [reviewTarget, setReviewTarget] = useState<{ subpath: string; name: string } | null>(null)
  /** 右栏页内预览的文件（null = 未选中）；高频「看一眼」不写 URL、不堆历史 */
  const [picked, setPicked] = useState<PickedFile | null>(null)

  /** 净宽（100vw − 助手宽度）：决定「文档在右」还是「文档通栏」（见 use-net-width） */
  const netWidth = useNetWidth()
  const dockedViewport = useDockedViewport()
  const docSideBySide = Boolean(picked) && netWidth >= DOC_SIDE_BY_SIDE_MIN
  /**
   * 文档对照形态：展开 + 净宽不足时，文档通栏置顶、事实卡退到其下。
   *
   * 只在宽屏（≥1280，详情页助手恒并排让位）成立——窄屏本来就该竖排，且助手此时
   * 是盖在页面上的覆盖层、设不了 CSS 变量。
   */
  const focusDoc = Boolean(picked) && dockedViewport && !docSideBySide

  const svc = useServiceItems('contract', deal?.id ?? null, { sourceSubpath: manualSource })
  const serviceItems = svc.items
  /**
   * 专项服务：阶段树 + 交付物（54 号原型脊椎）。两类非诉都调它（就是两次读请求），
   * 但只有专项页渲染——放在组件顶层是为了让分流不靠条件 Hook。
   */
  const special = useSpecialPhases('contract', deal?.id ?? null)
  const isSpecial = deal?.caseType === 'special'

  const openPreview = useCallback((f: PickedFile) => setPicked(f), [])

  useDealCopilotContext(deal, '非诉项目详情')

  const tree = special.tree
  /** 阶段目录里已有的文件数（元信息「N 个文件」）：展开行时按实际交付物计数 */
  const fileCountOf = useCallback(
    (node: PhaseNode) => flattenTree([node]).reduce((s, x) => s + x.node.deliverables.filter((d) => !d.planned).length, 0),
    [],
  )

  /**
   * 「从 0 起草」/「＋ 起草」的落点：把计划项写进目标阶段、展开它，并**直接打开
   * 编辑器**——律师此刻要的是「马上改」，不是回到列表自己去找文件。
   */
  const draftIntoPhase = useCallback(
    (phaseKey: string, name: string) => {
      const next = patchPhase(addDeliverable(tree, phaseKey, name), phaseKey, { open: true })
      void special.saveStages(next)
      const hit = flattenTree(next).find((x) => x.node.key === phaseKey)
      const created = hit?.node.deliverables.at(-1)
      toast.success(`已起草《${name.replace(/^《|》$/g, '')}》`, {
        description: `落到「${hit?.node.name ?? ''}」，保存后即进入编辑器`,
      })
      if (created?.subpath) openPreview({ subpath: created.subpath, name: created.name })
    },
    [tree, special, openPreview],
  )

  /** 右栏事实卡的完整入参（未预览 / 退到左栏底部两处都要用） */
  const railProps = {
    deadlines,
    today: d.today,
    contactGroups: contacts,
    team: deal?.team ?? [],
    deal: deal!,
    moneyRows: money,
    onOpenFile: openPreview,
    onReviewFile: (f: { subpath: string; name: string }) => setReviewTarget(f),
    onAddDue: () => soonToast('新增期限'),
    onAddPayment: () => setPayOpen(true),
    onOpenInvoices: () => setInvoiceOpen(true),
    // 发票关联/解除改了合同的开票金额：刷新合同（统计格、收款徽标、案件卡的钱）
    onMoneyChanged: () => (deal ? refetchContractAndCases(qc, deal.id) : undefined),
  }

  /**
   * 点右栏派生目录 → 展开该目录里第一份可预览的文件。
   *
   * 目录是阶段派生出来的，可能还没建（律师刚设计的阶段）或只有子目录；读不到
   * 就给一句明确提示，不静默什么都不发生。
   */
  const openFolderFromTree = useCallback(
    async (folder: string) => {
      if (!deal) return
      try {
        const res = await listFolderEntries('contract', deal.id, folder)
        const file = (res.files ?? [])[0]
        if (!file) {
          toast.info(`「${folder}」目录里还没有文件`, { description: '把交付物拖进合同文件夹后即可点开' })
          return
        }
        openPreview({ subpath: file.subpath, name: file.name, size: file.size ?? undefined, modified_at: file.modified_at })
      } catch {
        toast.info(`「${folder}」目录还不存在`, { description: '保存阶段后系统会在合同文件夹里建同名目录' })
      }
    },
    [deal, openPreview],
  )

  if (!valid) return <Navigate to="/projects" replace />
  if (d.isLoading) {
    return (
      <div className="flex flex-col items-center gap-2 py-[90px] text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        正在加载项目…
      </div>
    )
  }
  if (d.error || !deal) {
    return <DetailError error={d.error ?? '项目不存在'} onRetry={() => d.refetch()} />
  }

  return (
    <main className="app-page-enter @container mx-auto max-w-[1280px] px-[30px] pt-[26px] pb-20 min-[1400px]:max-w-[1400px] min-[1900px]:max-w-[1760px] min-[2400px]:max-w-[2200px] min-[2600px]:max-w-[2480px] max-[680px]:px-3 max-[680px]:pt-4">
      <DetailHeader deal={deal} onAddDue={() => soonToast('新增期限')} onAddLog={() => soonToast('记办案日志')} />

      {/* 周期轴：常法 → 服务期 + 事项刻度；专项 → 项目周期 + 阶段里程碑 */}
      {deal.from && deal.to && (
        <div className="mb-[18px]">
          {isSpecial ? (
            <TermBar
              from={deal.from}
              to={deal.to}
              today={todayStr}
              title="项目周期"
              milestones={flattenTree(tree)
                .filter((x) => !!x.node.startDate)
                .map((x) => ({ date: x.node.startDate, title: x.node.name, state: phaseTone(x.node.state) }))}
              legend={
                flattenTree(tree).length > 0
                  ? `阶段 ${flattenTree(tree).filter((x) => x.node.state === 'done').length} / ${flattenTree(tree).length}`
                  : undefined
              }
            />
          ) : (
            <TermBar
              from={deal.from}
              to={deal.to}
              today={todayStr}
              events={serviceItems.map((i) => ({ date: i.date, title: i.title }))}
            />
          )}
        </div>
      )}

      {/* 栅格三态（就地编辑）：① 左内容 + 右事实卡；② 净宽≥1100 时文档在右、事实卡退左栏底部；
          ③ 净宽不足时文档通栏、事实卡在其下。判定口径与实现见 DealDocLayout / use-net-width。 */}
      <DealDocLayout
        picked={picked}
        docSideBySide={docSideBySide}
        focusDoc={focusDoc}
        ownerId={deal.id}
        onClose={() => setPicked(null)}
        onSaved={() => void d.refetch()}
        onReview={(f) => setReviewTarget(f)}
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
          />
        }
      >
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
                  onClick={() => soonToast('新建' + next)}
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
        onReviewStart={(f) => setReviewTarget(f)}
      />

      <PaymentDialog
        open={payOpen}
        contractId={deal.id}
        fixedAmount={deal.amountNum}
        receivedAmount={Number(deal.totalReceived?.replace(/[^\d.]/g, '') || 0)}
        onClose={() => setPayOpen(false)}
        onSaved={() => void d.refetch()}
      />

      <InvoicePoolDialog open={invoiceOpen} contractId={deal.id} onClose={() => setInvoiceOpen(false)} />
    </main>
  )
}

/** 阶段状态 → 周期轴刻度语义（done 对齐 term-timeline 的 ok） */
function phaseTone(state: PhaseNode['state']): 'ok' | 'doing' | 'todo' {
  if (state === 'done') return 'ok'
  return state === 'doing' ? 'doing' : 'todo'
}
