import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate, useParams } from 'react-router'
import { Loader2 } from 'lucide-react'

import { useMediaQuery } from '@/hooks/use-media'

import { ambiguousStages, chainSteps, chainSummary } from './detail-domain'
import { CaseSection, NextStageRow } from './CaseSection'
import { ChainStepper } from './ChainStepper'

import { DetailHeader } from './DetailHeader'
import { DetailRail } from './DetailRail'
import { FilePreviewCard } from './FilePreviewCard'
import { ContractFileOverlays } from './ContractFileOverlays'
import { ResizeHandle } from './ResizeHandle'
import { useResizablePanel } from './use-resizable-panel'
import { soonToast, useDealCopilotContext, useDealDetailPage } from './use-deal-detail-page'
import { PaymentDialog } from './PaymentDialog'
import { InvoicePoolDialog } from './InvoicePoolDialog'
import { DetailError } from './ui'
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
  const { valid, d, deal, plan, ordered, deadlines, contacts, money, next } = useDealDetailPage(id)
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
  /** 合同文件夹的文件 → 预览（右栏合同文件夹树） */
  const openContractFile = useCallback(
    (f: { subpath: string; name: string; size?: number; modified_at?: string; mtime?: number }) => {
      setPicked({ ...f, kind: 'contract', ownerId: deal?.id ?? 0 })
    },
    [deal?.id],
  )
  /** 案件文件夹的文件 → 预览（左栏案件卡；ownerId 是案件 id）。柯里化：案件 id 在 map 里 */
  const openCaseFile =
    (caseId: number) => (f: { subpath: string; name: string; size?: number; modified_at?: string; mtime?: number }) => {
      setPicked({ ...f, kind: 'case', ownerId: caseId })
    }

  /** 预览栏宽度：可拖拽、记住偏好（与非诉页同一套 hook，各记各的 key） */
  const panel = useResizablePanel({
    storageKey: 'fachuan:deal:preview-width',
    defaultWidth: 720,
    min: 360,
    maxRatio: 0.78,
    layoutKey: picked ? 'split' : 'stacked',
  })
  const {
    effectiveWidth: panelEffectiveWidth,
    stacked: panelStacked,
    dragging: panelDragging,
    containerRef: panelContainerRef,
    onPointerDown: panelPointerDown,
    setWidth: panelSetWidth,
  } = panel

  const steps = useMemo(() => chainSteps(plan), [plan])
  const ambiguous = useMemo(() => ambiguousStages(plan), [plan])

  /**
   * 「文档对照」形态（与非诉页同一判定，详见 NonLitDetailPage 同名注释）：
   * 合同预览与并排 AI 助手同开、净宽不足时，右栏只留「预览 + 合同文件夹」，
   * 期限/当事人/…/合同要素等档案节整体隐藏，且文档列提前到最前紧贴助手。
   */
  const dockableViewport = useMediaQuery('(min-width: 1280px)')
  const focusDoc = Boolean(picked) && panelStacked && dockableViewport

  /* 创建类动作：记日志 / 新增期限 / 新建下一程序案件仍占位；记收款已接真实表单 */
  const soon = useCallback((what: string) => soonToast(what), [])
  const onAddLog = useCallback(() => soon('记办案日志'), [soon])
  const onAddDue = useCallback(() => soon('新增期限'), [soon])
  const onCreateNext = useCallback(() => soon('新建' + (next ?? '') + '案件'), [soon, next])

  /** 记收款弹窗：粘贴到账短信 / 拖发票进来（见 PaymentDialog） */
  const [payOpen, setPayOpen] = useState(false)
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
    return (
      <div className="flex flex-col items-center gap-2 py-[90px] text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        正在加载委托…
      </div>
    )
  }
  if (d.error || !deal) {
    return <DetailError error={d.error ?? '委托不存在'} onRetry={() => d.refetch()} />
  }
  return (
    <main className="app-page-enter mx-auto max-w-[1280px] px-[30px] pt-[26px] pb-20 min-[1400px]:max-w-[1400px] min-[1900px]:max-w-[1760px] min-[2400px]:max-w-[2200px] min-[2600px]:max-w-[2480px] max-[680px]:px-3 max-[680px]:pt-4">
      <DetailHeader
        deal={deal}
        onAddDue={onAddDue}
        onAddLog={onAddLog}
      />

      <ChainStepper steps={steps} summary={chainSummary(plan)} onJump={jump} />

      {/* AI 助手入口只在导航栏（全局侧边栏 CopilotPanel，⌘J 同效）：页面内既不挂
          对话区、页头也不放按钮，避免与导航栏入口重复 */}
      {/* 与诉讼页一致：一旦在预览合同就扩宽右栏，让 OnlyOffice 有足够宽度
          渲染 A4 正文（窄栏里只看得到半行字，等于没预览）。
          有预览时用 flex + 可拖分隔条，宽度交给用户，写死断点只能猜折中值。
          横/竖排由 panelStacked（容器净宽）决定而非视口媒体查询——并排 AI 助手
          会让位掉数百像素净宽，视口量不到它（详见「文档对照」注释）。 */}
      <div
        ref={panelContainerRef}
        className={
          picked
            ? panelStacked
              ? 'flex flex-col gap-[18px]'
              : 'flex items-start gap-[8px]'
            : panelStacked
              ? 'grid grid-cols-1 items-start gap-[18px]'
              : 'grid items-start gap-[18px] grid-cols-[minmax(0,1fr)_400px] min-[1900px]:grid-cols-[minmax(0,1fr)_440px] min-[2400px]:grid-cols-[minmax(0,1fr)_480px]'
        }
      >
        {/* 文档对照形态：文档列（右栏卡里的预览）提前到最前，案件程序链沉底 */}
        {focusDoc && picked && (
          <div className="min-w-0">
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
              onOpenFile={openContractFile}
              onReviewFile={(f) => setReviewTarget(f)}
              factsHidden
              folderPreview={
                <div className="mb-2.5 flex h-[min(70vh,720px)] min-h-[420px] flex-col">
                  <FilePreviewCard
                    kind={picked.kind}
                    ownerId={picked.ownerId}
                    file={picked}
                    onClose={() => setPicked(null)}
                    onSaved={() => void d.refetch()}
                    onReview={picked.kind === 'contract' ? (f) => setReviewTarget(f) : undefined}
                  />
                </div>
              }
            />
          </div>
        )}

        <div className="min-w-0 flex-1">
          {d.casesError ? (
            <div className="rounded-[12px] border border-destructive/30 bg-destructive/5 px-5 py-4 text-sm text-destructive">
              {d.casesError} ·{' '}
              <button type="button" className="cursor-pointer underline underline-offset-3" onClick={() => d.refetch()}>
                重试
              </button>
            </div>
          ) : plan.length === 0 ? (
            <div className="rounded-[12px] border border-border bg-card px-5 py-8 text-center text-[13px] text-muted-foreground shadow-sm">
              合同没有勾选代理阶段，也还没有立案的程序
            </div>
          ) : (
            /* 超宽屏瀑布流两列：卡片高度本就不同，columns 顺次填充不留 grid 行对齐的空格子。
               仅两案及以上才分栏——单案分栏会让卡片只占半宽、右侧留白反而更空 */
            <div
              className={
                'space-y-[18px] ' +
                (ordered.length >= 2
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
                    selectedSubpath={picked?.kind === 'case' && picked.ownerId === c.id ? picked.subpath : null}
                  />
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

        {picked && !focusDoc && (
          <ResizeHandle
            dragging={panelDragging}
            hidden={panelStacked}
            onPointerDown={panelPointerDown}
            onKeyAdjust={(dir) => panelSetWidth((w) => Math.max(320, w + dir * 40))}
            label="调整预览栏宽度"
          />
        )}

        {!focusDoc && (
          <div
            className="min-w-0"
            style={picked && panelEffectiveWidth ? { width: panelEffectiveWidth, flex: 'none' } : undefined}
          >
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
              onOpenFile={openContractFile}
              onReviewFile={(f) => setReviewTarget(f)}
              folderPreview={
                picked ? (
                  <div className="mb-2.5 flex h-[min(70vh,720px)] min-h-[420px] flex-col">
                    <FilePreviewCard
                      kind={picked.kind}
                      ownerId={picked.ownerId}
                      file={picked}
                      onClose={() => setPicked(null)}
                      onSaved={() => void d.refetch()}
                      onReview={picked.kind === 'contract' ? (f) => setReviewTarget(f) : undefined}
                      />
                  </div>
                ) : null
              }
            />
          </div>
        )}
      </div>

      <ContractFileOverlays
        ownerId={deal.id}
        client={deal.parties?.client}
        reviewTarget={reviewTarget}
        onReviewClose={() => setReviewTarget(null)}
        onReviewStart={(f) => setReviewTarget(f)}
      />

      {/* 记收款：粘贴到账短信 / 拖发票。保存后刷新合同，右栏收费节即时更新 */}
      <PaymentDialog
        open={payOpen}
        contractId={deal.id}
        fixedAmount={deal.amountNum}
        receivedAmount={Number(deal.totalReceived?.replace(/[^\d.]/g, '') || 0)}
        onClose={() => setPayOpen(false)}
        onSaved={() => void d.refetch()}
      />

      {/* 先开票后付款：票挂合同名下；关闭即失效待核销缓存，右栏计数同步 */}
      <InvoicePoolDialog open={invoiceOpen} contractId={deal.id} onClose={() => setInvoiceOpen(false)} />
    </main>
  )
}
