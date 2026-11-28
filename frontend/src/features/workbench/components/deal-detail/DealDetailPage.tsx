import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Navigate, useParams } from 'react-router'

import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { CaseVerifyCard } from '@/features/material-prep'

import { ambiguousStages, caseBranches, chainShape, chainSteps, chainSummary, trimPlan } from './detail-domain'
import { CaseSection, NextStageRow } from './CaseSection'
import { CaseOverview } from './CaseOverview'
import { ChainStepper } from './ChainStepper'

import { DetailHeader } from './DetailHeader'
import { DetailRail } from './DetailRail'
import { CaseActionsSheet } from './CaseActionsSheet'
import { DealDetailDialogs } from './DealDetailDialogs'
import { ContractFileOverlays } from './ContractFileOverlays'
import { DealDocLayout } from './DealDocLayout'
import type { FolderEntryMutation } from './folder-tree-types'
import { useDocPreview } from './use-doc-preview'
import { useDraftDialog } from './use-draft-dialog'
import { useDealCopilotContext, useDealDetailPage } from './use-deal-detail-page'
import { refetchContractAndCases } from './refetch-contract'
import { Card, DetailError } from './ui'
import type { FolderOwnerKind } from '../../api'

/**
 * 正在预览的文件：诉讼页有两个文件来源——右栏的合同文件夹（kind=contract）
 * 与案件卡里的案件文件夹（kind=case，诉讼项目的文件主体）。预览画布同一套
 * （FilePreviewCard + OnlyOffice），kind/ownerId 决定取文件与保存回写走哪条通道
 * （后端 OnlyOffice 域注册表按路径前缀分发：/contracts/ 与 /cases/）。
 */
type PickedFile = {
  kind: FolderOwnerKind
  ownerId: number
  subpath: string
  name: string
  size?: number
  modified_at?: string
  mtime?: number
}

/**
 * 52 号定则：过去在时间轴（案件节日志按日叙事），未来在右栏（期限只在这里预警）。
 * 左列只放案件本身（程序链 + 下一步），合同层面的当事人/收款/补充协议/要素全在右栏卡里。
 * 数据组装与助手上下文绑定在 use-deal-detail-page，与 NonLitDetailPage 共用。
 */
export function DealDetailPage() {
  const { id } = useParams<{ id: string }>()
  /**
   * 正在发起审查的文件（null = 抽屉关闭）。
   * 诉讼页的合同也要能走 AI 审查——起诉状/和解协议同样是「AI 出建议、律师逐条决策」。
   */
  const [reviewTarget, setReviewTarget] = useState<{ subpath: string; name: string } | null>(null)
  const { contractId, valid, d, deal, plan, ordered, deadlines, contacts, money, next } = useDealDetailPage(id)
  /** stepper 跳转后的短暂高亮环（案件 id） */
  const [hl, setHl] = useState<number | null>(null)
  /**
   * 「树里这一条是不是正在预览的那份」——诉讼页按当前选中文件的 kind/ownerId 比，
   * 所以案件文件夹与合同文件夹共用同一个判定。
   */
  const pickedStillMine = useCallback(
    (ev: FolderEntryMutation, cur: PickedFile) => cur.kind === ev.kind && cur.ownerId === ev.ownerId,
    [],
  )

  const {
    picked,
    setPicked,
    immersive,
    setImmersive,
    closePreview,
    onFolderMutated,
    docSideBySide,
    doc,
  } = useDocPreview<PickedFile>({ isStale: pickedStillMine })
  const guardDirty = doc.guard
  const markDirty = doc.markDirty

  /** 合同文件夹的文件 → 预览（右栏合同文件夹树） */
  const openContractFile = useCallback(
    (f: { subpath: string; name: string; size?: number; modified_at?: string; mtime?: number }) => {
      guardDirty(() => setPicked({ ...f, kind: 'contract', ownerId: deal?.id ?? 0 }))
    },
    // setPicked 是 useState 的 dispatcher（引用恒定），列进依赖只为满足 exhaustive-deps
    [deal?.id, guardDirty, setPicked],
  )
  /** 案件文件夹的文件 → 预览（左栏案件卡；ownerId 是案件 id）。柯里化：案件 id 在 map 里 */
  const openCaseFile =
    (caseId: number) =>
    (f: { subpath: string; name: string; size?: number; modified_at?: string; mtime?: number }) => {
      guardDirty(() => setPicked({ ...f, kind: 'case', ownerId: caseId }))
    }

  /** 「生成文书」弹窗：成稿落回本页画布（同样走脏标记拦截） */
  const draft = useDraftDialog((f) => guardDirty(() => setPicked(f)))

  /**
   * 新案件的默认名称。有双方当事人就拼「甲诉乙+案由」（律师的习惯写法），
   * 否则退回「合同名·阶段」——一律给可改的默认值，不让律师从空框开始打字。
   */
  const defaultCaseName = useMemo(() => {
    const cause = ordered.at(-1)?.cause ?? ''
    const a = deal?.parties?.client
    const b = deal?.parties?.other
    if (a && b) return `${a}诉${b}${cause}`
    return `${deal?.client ?? ''}·${next ?? ''}`
  }, [deal?.parties?.client, deal?.parties?.other, deal?.client, ordered, next])

  /**
   * 顶部那块画什么，由「这个委托下有几条程序线」决定（判据见 caseBranches / chainShape）：
   *
   * - `single`（一个案件）→ **什么都不画**。单案的「一审 · 在办 · 顺德法院」在下面那张
   *   案件卡的卡头与 meta 行里一个字段不少，进度条只是把它抄了一遍；「下一步是什么」
   *   由最下方的 NextStageRow 回答，且带按钮，比一个空心点有用。
   * - `chain`（多案但在同一条线）→ 横向进度条，砍掉永远空着的节点（trimPlan）。
   * - `multi`（多条互不相干的线）→ 一案一行的总览（CaseOverview）。
   * - `none`（一个案件都还没立）→ 只有合同勾了阶段时才画（那是**约定的代理范围**，
   *   与「走这边」无关）；阶段也没勾就和左列的空态卡重复，不画。
   */
  const branches = useMemo(() => caseBranches(ordered), [ordered])
  const shape = chainShape(branches)
  const showStepper = shape === 'chain' || (shape === 'none' && plan.length > 0)
  const steps = useMemo(() => chainSteps(trimPlan(plan)), [plan])
  const ambiguous = useMemo(() => ambiguousStages(plan), [plan])

  /* 三个创建动作都接了真实表单：记日志 / 新增期限 / 新建下一程序案件
     （见 AddLogDialog / AddDeadlineDialog / AddCaseDialog） */
  const onCreateNext = useCallback(() => setCaseOpen(true), [])

  /** 正在记日志的案件（null = 弹窗关闭）。日志归属**具体案件**，所以带 id + 程序名 */
  const [logTarget, setLogTarget] = useState<{ id: number; label: string } | null>(null)
  /** 新增期限弹窗（右栏「期限」节的 ＋ 新增） */
  const [deadlineOpen, setDeadlineOpen] = useState(false)
  /** 新建下一程序案件弹窗 */
  const [caseOpen, setCaseOpen] = useState(false)
  /** 「办理」抽屉：立案 / 担保 / OA / 归档（四件事一个入口，案件卡不变工具栏） */
  const [actionsFor, setActionsFor] = useState<{ id: number; label: string } | null>(null)
  /** 刚建好的案件 id：等它出现在 ordered 里再滚过去高亮（列表刷新是异步的） */
  const [newCaseId, setNewCaseId] = useState<number | null>(null)
  /**
   * 期限/日志写完后要刷的三处：合同（合同直挂期限）、案件（时间轴里的日志与日志级
   * 期限）、案件直挂提醒（开庭这类）——缺一处就会出现「记了但列表里没有」。
   */
  const queryClient = useQueryClient()
  const onScheduleChanged = useCallback(() => {
    refetchContractAndCases(queryClient, contractId)
    void queryClient.invalidateQueries({ queryKey: ['workbench', 'case-reminders', contractId] })
  }, [queryClient, contractId])

  /** 记收款弹窗：粘贴到账短信 / 拖发票进来（见 PaymentDialog） */
  const [payOpen, setPayOpen] = useState(false)
  /**
   * 收费节里的写操作（发票关联/解除/上传）完成后刷新合同 + 案件。
   *
   * 这些动作改的是**合同**上的开票金额与开票状态（统计格、收款徽标、案件卡的钱
   * 都由合同数据算出），只刷收费节自己的发票列表会出现「票挂上了、已开票还是
   * ¥0」的半新半旧状态，律师只能手动刷页面。刷新口径见 refetch-contract.ts。
   */
  const onMoneyChanged = useCallback(() => {
    refetchContractAndCases(queryClient, contractId)
  }, [queryClient, contractId])

  const onAddPayment = useCallback(() => setPayOpen(true), [])

  /** 传发票弹窗：先开票后付款的入口（票挂合同名下，见 InvoicePoolDialog） */
  const [invoiceOpen, setInvoiceOpen] = useState(false)
  const onOpenInvoices = useCallback(() => setInvoiceOpen(true), [])

  // 本页就是「这个委托」——把全局助手绑到该委托的业务上下文（详见 use-deal-detail-page）
  useDealCopilotContext(deal, '委托详情')

  const jump = useCallback((caseId: number) => {
    document.getElementById('case-' + caseId)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setHl(caseId)
  }, [])

  /**
   * 建案成功后滚过去。建完立刻 scrollIntoView 是找不到节点的（案件列表还在重取），
   * 所以以「新 id 真的出现在 ordered 里」为触发条件，出现一次即用掉这次意图。
   */
  useEffect(() => {
    if (newCaseId == null) return
    if (!ordered.some((c) => c.id === newCaseId)) return
    jump(newCaseId)
    setNewCaseId(null)
  }, [newCaseId, ordered, jump])
  useEffect(() => {
    if (hl == null) return
    const t = window.setTimeout(() => setHl(null), 1800)
    return () => window.clearTimeout(t)
  }, [hl])

  if (!valid) return <Navigate to="/projects" replace />
  if (d.isLoading) {
    return <LoadingBlock text="正在加载委托…" className="min-h-[calc(100vh-100px)]" />
  }
  if (d.error || !deal) {
    return <DetailError error={d.error ?? '委托不存在'} onRetry={() => d.refetch()} />
  }
  return (
    <main className="app-page-enter @container mx-auto max-w-[1280px] px-[30px] pt-[26px] pb-20 min-[1400px]:max-w-[1400px] min-[1900px]:max-w-[1760px] min-[2400px]:max-w-[2200px] min-[2600px]:max-w-[2480px] max-[680px]:px-3 max-[680px]:pt-4">
      <DetailHeader deal={deal} />

      {shape === 'multi' ? (
        <CaseOverview cases={ordered} onJump={jump} />
      ) : showStepper ? (
        <ChainStepper steps={steps} summary={chainSummary(plan)} onJump={jump} />
      ) : null}

      {/* AI 助手入口只在导航栏（全局侧边栏 CopilotPanel，⌘J 同效）：页面内既不挂
          对话区、页头也不放按钮，避免与导航栏入口重复 */}
      {/* 文档单独成栏（四态见 DealDocLayout）。要点是**档案卡不再跟着文档变宽**：
          此前预览长在档案卡里，为了塞下 A4 只能把整张卡拉到 720–780px，期限/
          当事人/收费被摊成一排空行，看着像侧栏被人硬拽开；而卡里那点高度
          （70vh 再扣 DS 工具栏）连一页都放不下。
          横/竖排与文档宽度归 DealDocLayout；这里只负责「案件链写在左列」。 */}
      <DealDocLayout
        kind={picked?.kind ?? 'contract'}
        picked={picked}
        docSideBySide={docSideBySide}
        ownerId={picked?.ownerId ?? deal.id}
        widthStorageKey="fachuan:deal:preview-width"
        immersive={immersive}
        onToggleImmersive={() => setImmersive((v) => !v)}
        onClose={closePreview}
        onSaved={() => void d.refetch()}
        onReview={picked?.kind === 'contract' ? (f) => setReviewTarget(f) : undefined}
        onDirtyChange={markDirty}
        rail={
          <DetailRail
            deadlines={deadlines}
            today={d.today}
            contactGroups={contacts}
            team={deal.team}
            deal={deal}
            moneyRows={money}
            onAddDue={() => setDeadlineOpen(true)}
            onAddPayment={onAddPayment}
            onOpenInvoices={onOpenInvoices}
            onMoneyChanged={onMoneyChanged}
            onOpenFile={openContractFile}
            onReviewFile={(f) => setReviewTarget(f)}
            folderSelectedSubpath={picked?.kind === 'contract' ? picked.subpath : null}
            onFolderMutated={onFolderMutated}
          />
        }
      >
        <div className="min-w-0">
          {d.casesError ? (
            /* 案件列表错不能当空列表：律师会读成「本案没有程序」 */
            <ErrorBlock
              error={d.casesError}
              onRetry={() => d.refetch()}
              retryText="重试"
              className="px-5 py-4 text-sm"
            />
          ) : plan.length === 0 ? (
            <Card>
              <EmptyBlock className="px-5 py-8 text-[13px] text-muted-foreground">
                合同没有勾选代理阶段，也还没有立案的程序
              </EmptyBlock>
            </Card>
          ) : (
            /* 超宽屏瀑布流两列：卡片高度本就不同，columns 顺次填充不留 grid 行对齐的空格子。
               仅两案及以上才分栏——单案分栏会让卡片只占半宽、右侧留白反而更空 */
            <div
              className={
                'space-y-[18px] ' +
                (ordered.length >= 2 && !docSideBySide
                  ? 'min-[1900px]:columns-2 min-[1900px]:gap-[18px] min-[1900px]:space-y-0'
                  : '')
              }
            >
              {ordered.map((c) => (
                <div
                  key={c.id}
                  className={ordered.length >= 2 ? 'min-[1900px]:mb-[18px] min-[1900px]:break-inside-avoid' : ''}
                >
                  <CaseSection
                    c={c}
                    ambiguous={ambiguous.has(c.proc)}
                    highlighted={hl === c.id}
                    onAddLog={setLogTarget}
                    onOpenActions={setActionsFor}
                    onOpenFile={openCaseFile(c.id)}
                    onDraft={draft.openFor}
                    selectedSubpath={picked?.kind === 'case' && picked.ownerId === c.id ? picked.subpath : null}
                    onFolderMutated={onFolderMutated}
                  />
                  <CaseVerifyCard caseId={c.id} />
                </div>
              ))}
            </div>
          )}
          {next && !d.casesError && (
            <div className="mt-[18px]">
              <NextStageRow stage={next} onCreate={onCreateNext} />
            </div>
          )}
        </div>
      </DealDocLayout>

      <ContractFileOverlays
        ownerId={deal.id}
        client={deal.parties?.client}
        reviewTarget={reviewTarget}
        onReviewClose={() => setReviewTarget(null)}
      />

      <DealDetailDialogs
        contractId={contractId}
        deal={deal}
        ordered={ordered}
        next={next}
        defaultCaseName={defaultCaseName}
        payOpen={payOpen}
        onPayClose={() => setPayOpen(false)}
        onPaymentSaved={onMoneyChanged}
        invoiceOpen={invoiceOpen}
        onInvoiceClose={() => setInvoiceOpen(false)}
        caseOpen={caseOpen}
        onCaseClose={() => setCaseOpen(false)}
        onCaseSaved={(caseId) => {
          // 建完先刷合同+案件；滚动由上面的 effect 在「id 出现」时接手
          refetchContractAndCases(queryClient, contractId)
          setNewCaseId(caseId)
        }}
        logTarget={logTarget}
        onLogClose={() => setLogTarget(null)}
        onScheduleSaved={onScheduleChanged}
        deadlineOpen={deadlineOpen}
        onDeadlineClose={() => setDeadlineOpen(false)}
        doc={doc}
        draft={draft}
      />

      {/* 办理：一张网立案 / 申请担保 / OA 立案 / 项目归档 */}
      <CaseActionsSheet
        open={actionsFor !== null}
        onClose={() => setActionsFor(null)}
        caseId={actionsFor?.id ?? 0}
        caseLabel={actionsFor?.label ?? ''}
        contractId={contractId}
        onChanged={() => refetchContractAndCases(queryClient, contractId)}
      />
    </main>
  )
}
