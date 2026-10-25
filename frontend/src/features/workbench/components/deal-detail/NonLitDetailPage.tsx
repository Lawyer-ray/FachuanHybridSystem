import { useCallback, useMemo, useState } from 'react'
import { Navigate, useParams, useSearchParams } from 'react-router'
import { Loader2 } from 'lucide-react'

import { DetailHeader } from './DetailHeader'
import { DetailRail } from './DetailRail'
import { ContractFileOverlays } from './ContractFileOverlays'
import { FilePreviewCard } from './FilePreviewCard'
import { ServiceItemStream } from './ServiceItemStream'
import { useServiceItems } from './use-service-items'
import { TermBar } from './TermBar'
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
  const [searchParams, setSearchParams] = useSearchParams()
  /** 用户手动指定的事项源目录（null = 自动识别「办案」） */
  const [manualSource, setManualSource] = useState<string | null>(null)
  /** 今天（yyyy-mm-dd）：服务期条与「今天」高亮共用，跨天刷新时只改这一处 */
  const todayStr = useMemo(() => {
    const n = new Date()
    return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')}`
  }, [])
  /** 正在发起审查的文件（null = 抽屉关闭） */
  const [reviewTarget, setReviewTarget] = useState<{ subpath: string; name: string } | null>(null)
  /** 右栏页内预览的文件（null = 未选中）；高频「看一眼」不写 URL、不堆历史 */
  const [picked, setPicked] = useState<
    { subpath: string; name: string; size?: number; modified_at?: string; mtime?: number } | null
  >(null)
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

  /**
   * 升级到整页编辑器：写 `?file=`（可刷新/分享），并带上打开时的 mtime 做乐观锁。
   * 页内预览本身不写 URL——高频「看一眼」不该在浏览历史里堆记录。
   */
  const openEditor = useCallback(
    (f: { subpath: string; name: string }) => {
      const next = new URLSearchParams(searchParams)
      next.set('file', f.subpath)
      if (picked?.mtime !== undefined) next.set('mtime', String(picked.mtime))
      else next.delete('mtime')
      setSearchParams(next)
    },
    [searchParams, setSearchParams, picked],
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
    <main className="app-page-enter mx-auto max-w-[1280px] px-[30px] pt-[26px] pb-20 min-[1900px]:max-w-[1560px] max-[680px]:px-3 max-[680px]:pt-4">
      <DetailHeader deal={deal} onAddDue={() => soonToast('新增期限')} onAddLog={() => soonToast('记办案日志')} />

      {/* 服务期条：与下方服务事项流联动（事项按日落在轴上）。
          常法页最该回答「还剩多久、这一年忙不忙」，纯日期文字要读两遍才反应过来。 */}
      {deal.from && deal.to && (
        <div className="mb-[18px]">
          <TermBar from={deal.from} to={deal.to} today={todayStr} eventDates={serviceItems.map((i) => i.date)} />
        </div>
      )}

      {/* 左宽右窄（53 号原型）：左栏 = 服务事项流（本年度做了什么），
          右栏 = 合同要素 + 合同文件夹 + 预览。
          事项与文件夹不再是两套东西——文件夹是「交付物放在哪」，事项是
          「哪天为什么产生了它」，左栏看节奏、右栏取文件。 */}
      <div
        className={
          'grid items-start gap-[18px] max-[1100px]:grid-cols-1 ' +
          (picked
            ? 'grid-cols-[minmax(0,1fr)_minmax(520px,760px)]'
            : 'grid-cols-[minmax(0,1fr)_360px] min-[1900px]:grid-cols-[minmax(0,1fr)_400px]')
        }
      >
        {/* 左：服务事项流（本年度） */}
        <div className="min-w-0 space-y-[18px]">
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
            onOpenFile={(f: { subpath: string; name: string }) => setPicked(f)}
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
        </div>

        {/* 右：预览（选中时置顶）+ 合同要素/文件夹/事实卡 */}
        <div className="min-w-0 space-y-[18px]">
          {picked && (
            <div className="sticky top-[70px] flex h-[calc(100vh-100px)] min-h-[520px] flex-col">
              <FilePreviewCard
                kind="contract"
                ownerId={deal.id}
                file={picked}
                onClose={() => setPicked(null)}
                onOpenEditor={openEditor}
                onReview={(f) => setReviewTarget(f)}
              />
            </div>
          )}

          <DetailRail
            deadlines={deadlines}
            today={d.today}
            contactGroups={contacts}
            team={deal.team ?? []}
            deal={deal}
            moneyRows={money}
            showFolder
            folderOwnerId={deal.id}
            folderSelectedSubpath={picked?.subpath ?? null}
            onOpenFile={openPreview}
            onReviewFile={(f) => setReviewTarget(f)}
            onAddDue={() => soonToast('新增期限')}
            onAddPayment={() => soonToast('记收款')}
          />
        </div>
      </div>

      <ContractFileOverlays
        ownerId={deal.id}
        client={deal.parties?.client}
        other={deal.parties?.other}
        reviewTarget={reviewTarget}
        onReviewClose={() => setReviewTarget(null)}
        onReviewStart={(f) => setReviewTarget(f)}
      />
    </main>
  )
}
