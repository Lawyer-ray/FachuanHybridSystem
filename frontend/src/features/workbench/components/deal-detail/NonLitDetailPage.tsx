import { useCallback, useMemo, useState } from 'react'
import { Navigate, useParams } from 'react-router'
import { Loader2 } from 'lucide-react'

import { useMediaQuery } from '@/hooks/use-media'

import { DetailHeader } from './DetailHeader'
import { DetailRail } from './DetailRail'
import { ContractFileOverlays } from './ContractFileOverlays'
import { FilePreviewCard } from './FilePreviewCard'
import { ServiceItemStream } from './ServiceItemStream'
import { useServiceItems } from './use-service-items'
import { listFolderEntries } from '../../api'
import { TermBar } from './TermBar'
import { PaymentDialog } from './PaymentDialog'
import { ResizeHandle } from './ResizeHandle'
import { useResizablePanel } from './use-resizable-panel'
import { soonToast, useDealCopilotContext, useDealDetailPage } from './use-deal-detail-page'
import { Card, DetailError } from './ui'

/**
 * 非诉（常法）项目详情页。
 *
 * 与争议解决详情页的差别只在**左栏**：
 * - 诉讼：ChainStepper + 案件程序链（一审/二审/执行）
 * - 非诉：没有法院程序，左栏是这个项目的工作 —— 客户送回审的合同（合同文件夹）
 *
 * 右栏（期限 / 当事人 / 律师 / 收费 / 收款 / 合同要素 / 文件夹）完全复用，
 * 那些都是合同层面的事实，与诉讼非诉无关。数据组装与助手上下文绑定在
 * use-deal-detail-page，与 DealDetailPage 共用。
 */
export function NonLitDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { valid, d, deal, deadlines, contacts, money, next } = useDealDetailPage(id)

  /** 用户手动指定的事项源目录（null = 自动识别「办案」） */
  const [manualSource, setManualSource] = useState<string | null>(null)
  /** 今天（yyyy-mm-dd）：服务期条与「今天」高亮共用，跨天刷新时只改这一处 */
  const todayStr = useMemo(() => {
    const n = new Date()
    return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')}`
  }, [])
  /** 记收款弹窗（粘贴到账短信 / 拖发票） */
  const [payOpen, setPayOpen] = useState(false)
  /** 正在发起审查的文件（null = 抽屉关闭） */
  const [reviewTarget, setReviewTarget] = useState<{ subpath: string; name: string } | null>(null)
  /** 右栏页内预览的文件（null = 未选中）；高频「看一眼」不写 URL、不堆历史 */
  const [picked, setPicked] = useState<
    { subpath: string; name: string; size?: number; modified_at?: string; mtime?: number } | null
  >(null)

  /**
   * 预览栏宽度：可拖拽、记住偏好。
   *
   * 预览时右栏装的是 OnlyOffice，A4 正文在 600px 以下就开始缩字；而「多宽才够」
   * 因人的屏幕、系统缩放、阅读习惯而异。写死断点只能猜折中值，交给用户自己拖。
   */
  const panel = useResizablePanel({
    storageKey: 'fachuan:nonlit:preview-width',
    defaultWidth: 720,
    min: 360,
    // 事实卡已经移到左栏，右栏可以更宽——0.78 在 1440 屏给到 ~1090
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
  /**
   * 「文档对照」形态：合同预览与并排 AI 助手**同开**、页面净宽被挤到竖排阈值
   * （1100px）以下时触发——宽屏（≥1280，详情页助手恒并排让位）下净宽缩水
   * 只有助手并排一种成因。此时三栏（事项流 / 事实卡 / 文档）不可能同时摊开，
   * 硬塞会把事实卡挤成逐字竖排（实测左栏仅 78px）。让位策略：
   * - 事实卡（期限/当事人/…/合同要素，即右栏 DetailRail）整体隐藏——要看得
   *   收起助手或文档，空间立刻还给它们；
   * - 文档置顶全宽、紧贴助手（律师此时的注意力就是「左看文档右问 AI」）；
   * - 事项流沉底，滚动可达。
   * 净宽充裕（大屏或助手未开）时不触发，仍是「事项流 + 事实卡 + 可拖预览栏」。
   */
  const dockableViewport = useMediaQuery('(min-width: 1280px)')
  const focusDoc = Boolean(picked) && panelStacked && dockableViewport
  /**
   * 服务事项：直接从合同文件夹的「办案」目录读（目录名 = 事项名 + 日期）。
   * 找不到「办案」时由页面提示手动指定，不静默扫全盘。
   */
  const svc = useServiceItems('contract', deal?.id ?? null, { sourceSubpath: manualSource })
  const serviceItems = svc.items

  const openPreview = useCallback(
    (f: { subpath: string; name: string; size?: number; modified_at?: string; mtime?: number }) => {
      setPicked(f)
    },
    [],
  )

  // 非诉页同样把全局助手绑到该委托（欢迎页专属文案 / 新会话带 contract_id 归属）
  useDealCopilotContext(deal, '非诉项目详情')

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

  // 预览走整页替换（不开遮罩）：看合同需要宽度，半透明黑遮罩压在列表上又脏。
  // 由 URL 的 ?file= 驱动，刷新 / 后退 / 分享都能回到同一份。
  return (
    <main className="app-page-enter mx-auto max-w-[1280px] px-[30px] pt-[26px] pb-20 min-[1400px]:max-w-[1400px] min-[1900px]:max-w-[1760px] min-[2400px]:max-w-[2200px] min-[2600px]:max-w-[2480px] max-[680px]:px-3 max-[680px]:pt-4">
      <DetailHeader deal={deal} onAddDue={() => soonToast('新增期限')} onAddLog={() => soonToast('记办案日志')} />

      {/* 服务期条：与下方服务事项流联动（事项按日落在轴上）。
          常法页最该回答「还剩多久、这一年忙不忙」，纯日期文字要读两遍才反应过来。 */}
      {deal.from && deal.to && (
        <div className="mb-[18px]">
          <TermBar
            from={deal.from}
            to={deal.to}
            today={todayStr}
            events={serviceItems.map((i) => ({ date: i.date, title: i.title }))}
          />
        </div>
      )}

      {/* 左宽右窄（53 号原型）：左栏 = 服务事项流（本年度做了什么），
          右栏 = 合同要素 + 合同文件夹 + 预览。
          事项与文件夹不再是两套东西——文件夹是「交付物放在哪」，事项是
          「哪天为什么产生了它」，左栏看节奏、右栏取文件。 */}
      {/* 有预览时用 flex + 可拖分隔条：右栏装 OnlyOffice，宽度需求因人因屏而异，
          写死断点只能猜折中值。无预览时退回固定右栏（事实卡内容紧实，拖了没意义）。
          横/竖排由 panelStacked（容器净宽）决定而非视口媒体查询——并排 AI 助手
          会让位掉数百像素净宽，视口量不到它（破版实测见上方「文档对照」注释）。 */}
      <div
        ref={panelContainerRef}
        className={
          picked
            ? panelStacked
              ? 'flex flex-col gap-[18px]'
              : 'flex items-start gap-[8px]'
            : panelStacked
              ? 'grid grid-cols-1 items-start gap-[18px]'
              : 'grid items-start gap-[18px] grid-cols-[minmax(0,1fr)_360px] min-[1900px]:grid-cols-[minmax(0,1fr)_400px] min-[2400px]:grid-cols-[minmax(0,1fr)_440px]'
        }
      >
        {/* 文档对照形态：文档列提前到最前（紧贴右侧助手），事项流沉底 */}
        {focusDoc && picked && (
          <div className="min-w-0">
            <div className="sticky top-[70px] flex h-[calc(100vh-100px)] min-h-[520px] flex-col">
              <FilePreviewCard
                kind="contract"
                ownerId={deal.id}
                file={picked}
                onClose={() => setPicked(null)}
                onSaved={() => void d.refetch()}
                onReview={(f) => setReviewTarget(f)}
              />
            </div>
          </div>
        )}

        {/* 左：服务事项流（本年度） */}
        <div className="min-w-0 flex-1 space-y-[18px]">
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
            loadFiles={(subpath) =>
              listFolderEntries('contract', deal.id, subpath).then((r) => r.files ?? [])
            }
            onOpenDeliverable={(f) => setPicked(f)}
            onAdd={() => soonToast('记服务事项')}
          />

          {next && (
            <Card>
              <div className="px-[18px] py-3 text-[12.5px] text-muted-foreground">
                合同已勾选的下一程序：<b className="font-[620] text-foreground">{next}</b>
                <button
                  type="button"
                  className="ml-3 cursor-pointer underline underline-offset-3 hover:text-foreground"
                  onClick={() => soonToast('新建' + next)}
                >
                  新建{next}
                </button>
              </div>
            </Card>
          )}

          {/* 预览开启时事实卡落在左栏底部：右栏留给 OnlyOffice 一栏到底，
              两栏各自滚动互不干扰。文档对照形态下整体隐藏（见 focusDoc 注释）。 */}
          {picked && !focusDoc && (
            <DetailRail
              deadlines={deadlines}
              today={d.today}
              contactGroups={contacts}
              team={deal.team ?? []}
              deal={deal}
              moneyRows={money}
              showFolder={false}
              folderOwnerId={deal.id}
              folderSelectedSubpath={picked.subpath}
              onOpenFile={openPreview}
              onReviewFile={(f) => setReviewTarget(f)}
              onAddDue={() => soonToast('新增期限')}
              onAddPayment={() => setPayOpen(true)}
            />
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

        {/* 右：预览（选中时置顶）/ 未预览时放事实卡 */}
        {!focusDoc && (
          <div
            className="min-w-0 space-y-[18px]"
            style={picked && panelEffectiveWidth ? { width: panelEffectiveWidth, flex: 'none' } : undefined}
          >
            {picked && (
              <div className="sticky top-[70px] flex h-[calc(100vh-100px)] min-h-[520px] flex-col">
                <FilePreviewCard
                  kind="contract"
                  ownerId={deal.id}
                  file={picked}
                  onClose={() => setPicked(null)}
                  onSaved={() => void d.refetch()}
                  onReview={(f) => setReviewTarget(f)}
                  />
              </div>
            )}

            {/* 未预览时右栏就是事实卡（期限/当事人/收费/合同文件夹） */}
            {!picked && (
              <DetailRail
                deadlines={deadlines}
                today={d.today}
                contactGroups={contacts}
                team={deal.team ?? []}
                deal={deal}
                moneyRows={money}
                showFolder
                folderOwnerId={deal.id}
                folderSelectedSubpath={null}
                onOpenFile={openPreview}
                onReviewFile={(f) => setReviewTarget(f)}
                onAddDue={() => soonToast('新增期限')}
                onAddPayment={() => setPayOpen(true)}
              />
            )}
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

      <PaymentDialog
        open={payOpen}
        contractId={deal.id}
        fixedAmount={deal.amountNum}
        receivedAmount={Number(deal.totalReceived?.replace(/[^\d.]/g, '') || 0)}
        onClose={() => setPayOpen(false)}
        onSaved={() => void d.refetch()}
      />
    </main>
  )
}
