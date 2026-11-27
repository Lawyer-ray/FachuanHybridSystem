import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Navigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { DraftDialog } from '@/features/doc-generation'
import { CaseVerifyCard } from '@/features/material-prep'

import { ambiguousStages, chainSteps, chainSummary } from './detail-domain'
import { CaseSection, NextStageRow } from './CaseSection'
import { ChainStepper } from './ChainStepper'

import { DetailHeader } from './DetailHeader'
import { DetailRail } from './DetailRail'
import { ContractFileOverlays } from './ContractFileOverlays'
import { DealDocLayout, DOC_SIDE_BY_SIDE_MIN } from './DealDocLayout'
import type { FolderEntryMutation } from './folder-tree-types'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'
import { useDocDirtyGuard } from './use-doc-dirty-guard'
import { useNetWidth } from './use-net-width'
import { useDraftDialog } from './use-draft-dialog'
import { soonToast, useDealCopilotContext, useDealDetailPage } from './use-deal-detail-page'
import { PaymentDialog } from './PaymentDialog'
import { refetchContractAndCases } from './refetch-contract'
import { InvoicePoolDialog } from './InvoicePoolDialog'
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
   * 正在预览的文件（null = 未选中）。
   *
   * 预览在右栏就地展开（案件文件夹的树在左栏案件卡里）：律师核对原文时要
   * 对照同一栏的期限/当事人，跳走或弹窗都会让对照失效。合同文件与案件文件
   * 共用这块画布（见 PickedFile 注释），AI 审查入口只对合同文件开放——审查
   * 流水线从合同文件夹取文件。
   */
  const [picked, setPicked] = useState<PickedFile | null>(null)

  /**
   * 画布里有未保存的改动时，关文档 / 换文件先拦一下。
   *
   * 三个入口都能弄丢编辑：卡片右上角的 X、点文件夹树里的另一份、从案件卡打开
   * 别的文书。确认因此挂在页面这一层（见 useDocDirtyGuard 的注释）。
   */
  const doc = useDocDirtyGuard()
  const guardDirty = doc.guard
  const markDirty = doc.markDirty

  /**
   * 当前预览路径的实时快照。
   *
   * 文件夹树里改名/删除成功后要立刻判断「被弄掉的是不是正在看的那份」，
   * 而回调是事件式的、读 state 会读到上一轮渲染的值。
   */
  const pickedRef = useRef<PickedFile | null>(null)
  useEffect(() => {
    pickedRef.current = picked
  }, [picked])

  /**
   * 树里改名 / 删除后，把还在指着旧路径的画布关掉。
   *
   * 不处理的话：标题还是旧名字、高亮消失、画布仍可编辑，⌘S 打到一个不存在的
   * 文件上——律师看到的是「保存成功」，而内容根本没写进去。
   */
  const onFolderMutated = useCallback(
    (ev: FolderEntryMutation) => {
      const cur = pickedRef.current
      if (!cur || cur.kind !== ev.kind || cur.ownerId !== ev.ownerId) return
      const hit =
        ev.type === 'delete'
          ? cur.subpath === ev.subpath || cur.subpath.startsWith(ev.subpath + '/')
          : cur.subpath === ev.from || cur.subpath.startsWith(ev.from + '/')
      if (!hit) return
      setImmersive(false)
      setPicked(null)
      markDirty(false)
      toast.info(ev.type === 'delete' ? '正在预览的文件已被删除，预览已关闭' : '文件已改名，预览已关闭')
    },
    [markDirty],
  )

  /** 合同文件夹的文件 → 预览（右栏合同文件夹树） */
  const openContractFile = useCallback(
    (f: { subpath: string; name: string; size?: number; modified_at?: string; mtime?: number }) => {
      guardDirty(() => setPicked({ ...f, kind: 'contract', ownerId: deal?.id ?? 0 }))
    },
    [deal?.id, guardDirty],
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
   * 文档栏形态（与非诉页同一套判定，见 DealDocLayout 的四态表）：
   * 净宽够 → 文档在右（可拖宽）；净宽不够的宽屏 → 文档通栏置顶。
   * 判定用**净宽**而不是视口：并排 AI 助手会吃掉数百像素，问视口等于没问。
   */
  const netWidth = useNetWidth()
  const docSideBySide = Boolean(picked) && netWidth >= DOC_SIDE_BY_SIDE_MIN

  /**
   * 沉浸态（DealDocLayout 的 ④）：文档占满整宽与一屏高，案件链与档案排到其下。
   * 状态放在页面这一层：关掉文档时要一起复位，否则下一份文件打开就是全屏。
   */
  const [immersive, setImmersive] = useState(false)
  const closePreview = useCallback(() => {
    guardDirty(() => {
      setImmersive(false)
      setPicked(null)
    })
  }, [guardDirty, setImmersive, setPicked])

  const steps = useMemo(() => chainSteps(plan), [plan])
  const ambiguous = useMemo(() => ambiguousStages(plan), [plan])

  /* 创建类动作：记日志 / 新增期限 / 新建下一程序案件仍占位；记收款已接真实表单 */
  const soon = useCallback((what: string) => soonToast(what), [])
  const onAddLog = useCallback(() => soon('记项目日志'), [soon])
  const onAddDue = useCallback(() => soon('新增期限'), [soon])
  const onCreateNext = useCallback(() => soon('新建' + (next ?? '') + '案件'), [soon, next])

  /** 记收款弹窗：粘贴到账短信 / 拖发票进来（见 PaymentDialog） */
  const [payOpen, setPayOpen] = useState(false)
  const queryClient = useQueryClient()
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
  useEffect(() => {
    if (hl == null) return
    const t = window.setTimeout(() => setHl(null), 1800)
    return () => window.clearTimeout(t)
  }, [hl])

  if (!valid) return <Navigate to="/projects" replace />
  if (d.isLoading) {
    return <LoadingBlock text="正在加载委托…" className="py-[90px]" />
  }
  if (d.error || !deal) {
    return <DetailError error={d.error ?? '委托不存在'} onRetry={() => d.refetch()} />
  }
  return (
    <main className="app-page-enter @container mx-auto max-w-[1280px] px-[30px] pt-[26px] pb-20 min-[1400px]:max-w-[1400px] min-[1900px]:max-w-[1760px] min-[2400px]:max-w-[2200px] min-[2600px]:max-w-[2480px] max-[680px]:px-3 max-[680px]:pt-4">
      <DetailHeader
        deal={deal}
        onAddDue={onAddDue}
        onAddLog={onAddLog}
      />

      <ChainStepper steps={steps} summary={chainSummary(plan)} onJump={jump} />

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
            onAddDue={onAddDue}
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
                    onAddLog={onAddLog}
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

      {/* 记收款：粘贴到账短信 / 拖发票。保存后刷新合同，右栏收费节即时更新 */}
      <PaymentDialog
        open={payOpen}
        contractId={deal.id}
        fixedAmount={deal.amountNum}
        receivedAmount={Number(deal.totalReceived?.replace(/[^\d.]/g, '') || 0)}
        onClose={() => setPayOpen(false)}
        // 与「关联发票」同一口径：合同 + 案件 + 工作台列表一起刷。
        // 只 refetch 本页的话，退回列表 60s 内还是旧金额（staleTime），
        // 看起来像「记了收款但没记上」。
        onSaved={onMoneyChanged}
      />

      {/* 先开票后付款：票挂合同名下；关闭即失效未关联缓存，右栏计数同步 */}
      <InvoicePoolDialog open={invoiceOpen} contractId={deal.id} onClose={() => setInvoiceOpen(false)} />

      {/* 未保存改动的确认：拦的是「关文档 / 换文件」，不是页面级导航 */}
      <UnsavedChangesDialog open={doc.pending} onStay={doc.stay} onLeave={doc.leave} />

      {/* 一句话生成文书。只有诉讼分支挂它：已上线的 spec 都是案件文书，合同文件夹
          模板里没有对应落位节点（传 contract 侧会得到 created=false + 原因） */}
      <DraftDialog
        open={draft.caseId != null}
        onOpenChange={(v) => { if (!v) draft.close() }}
        caseId={draft.caseId}
        onCreated={draft.onCreated}
      />
    </main>
  )
}
