import { useCallback, useMemo, useState } from 'react'
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router'
import { Loader2 } from 'lucide-react'

import { ReviewLaunchDrawer } from '@/features/contract-review'
import { withDownloadTicket } from '@/lib/download-ticket'
import { folderFileUrl } from '../../api'
import { DetailHeader } from './DetailHeader'
import { DetailRail } from './DetailRail'
import { FilePreview } from './FilePreview'
import { FolderTree } from './FolderTree'
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
  const navigate = useNavigate()
  /** 正在发起审查的文件（null = 抽屉关闭） */
  const [reviewTarget, setReviewTarget] = useState<{ subpath: string; name: string } | null>(null)
  /**
   * 正在预览的文件 —— 由 URL 的 `?file=` 驱动，不是组件 state。
   *
   * 用 state 的后果：刷新就丢、发不出链接、浏览器后退直接退出项目页。
   * 看合同时常要「刷新一下」「发同事看一眼」「对照另一份新开标签」，都做不到。
   * 用 query 而不是路径段：subpath 含 `/` 与中文，塞进路径段要处理 `%2F`，
   * 两边都容易踩坑。
   */
  const [searchParams, setSearchParams] = useSearchParams()
  const previewFile = useMemo(() => {
    const subpath = searchParams.get('file')
    if (!subpath) return null
    const name = subpath.split('/').pop() || subpath
    // mtime 只在当场点击时有（做保存乐观锁）；刷新后没有就不带，退化为不校验
    const mtimeRaw = searchParams.get('mtime')
    const mtime = mtimeRaw ? Number(mtimeRaw) : undefined
    return { subpath, name, mtime }
  }, [searchParams])

  const openPreview = useCallback(
    (f: { subpath: string; name: string; mtime?: number }) => {
      const next = new URLSearchParams(searchParams)
      next.set('file', f.subpath)
      if (f.mtime !== undefined) next.set('mtime', String(f.mtime))
      else next.delete('mtime')
      setSearchParams(next)
    },
    [searchParams, setSearchParams],
  )

  const closePreview = useCallback(() => {
    const next = new URLSearchParams(searchParams)
    next.delete('file')
    next.delete('mtime')
    // replace: 关预览不该在历史里多压一条（后退应该退出项目页）
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

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
  if (previewFile) {
    return (
      <FilePreview
        kind="contract"
        ownerId={deal.id}
        file={previewFile}
        onBack={closePreview}
        onReview={(f) => {
          // 预览 → 审查：先退预览，免得两个界面堆着
          closePreview()
          setReviewTarget(f)
        }}
        onSaved={() => void d.refetch()}
      />
    )
  }

  return (
    <main className="app-page-enter mx-auto max-w-[1280px] px-[30px] pt-[26px] pb-20 min-[1900px]:max-w-[1560px] max-[680px]:px-3 max-[680px]:pt-4">
      <DetailHeader deal={deal} onAddDue={() => soonToast('新增期限')} onAddLog={() => soonToast('记办案日志')} />

      <div className="grid grid-cols-[minmax(0,1fr)_400px] items-start gap-[18px] max-[1024px]:grid-cols-1 min-[1900px]:grid-cols-[minmax(0,1fr)_440px]">
        {/* 左：非诉的「工作」= 合同文件夹（客户送回审的合同都在里面） */}
        <div className="min-w-0 space-y-[18px]">
          <Card>
            <div className="flex items-center gap-2 border-b border-border-light px-[18px] py-[13px]">
              <span className="text-[12.5px] font-[650]">合同文件夹</span>
              <span className="text-[11px] text-muted-foreground">
                客户送回审的合同按日期归档在这里
              </span>
            </div>
            <div className="px-[18px] py-3">
              <FolderTree
                kind="contract"
                ownerId={deal.id}
                maxH="max-h-[520px]"
                onOpenFile={openPreview}
                onReviewFile={(f) => setReviewTarget(f)}
              />
            </div>
          </Card>

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

        {/* 右：与诉讼详情页完全同一套（都是合同层面的事实） */}
        <div className="min-w-0">
          <DetailRail
            deadlines={deadlines}
            today={d.today}
            contactGroups={contacts}
            team={deal.team ?? []}
            deal={deal}
            moneyRows={money}
            onAddDue={() => soonToast('新增期限')}
            onAddPayment={() => soonToast('记收款')}
          />
        </div>
      </div>

      {reviewTarget && (
        <ReviewLaunchDrawer
          open
          fileName={reviewTarget.name}
          loadFile={async () => {
            // 合同文件夹里的文件要带下载票据（浏览器原生请求带不上 Authorization 头）
            const url = await withDownloadTicket(
              folderFileUrl('contract', deal.id, reviewTarget.subpath),
            )
            const res = await fetch(url)
            if (!res.ok) throw new Error('读取合同文件失败')
            return res.arrayBuffer()
          }}
          parties={{ party_a: deal.parties?.client, party_b: deal.parties?.other }}
          partyHint={`AI 依据：合同抬头与历史来稿都指向「${deal.client}」为我方委托，如判断有误请改。`}
          onClose={() => setReviewTarget(null)}
          onStarted={(taskId) => {
            setReviewTarget(null)
            void navigate(`/projects/${deal.id}/review/${taskId}`)
          }}
        />
      )}
    </main>
  )
}
