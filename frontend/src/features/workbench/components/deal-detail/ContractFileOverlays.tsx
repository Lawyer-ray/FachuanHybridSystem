import { useNavigate } from 'react-router'

import { ReviewLaunchDrawer } from '@/features/contract-review'
import { projectReview } from '@/app/paths'
import { withDownloadTicket } from '@/lib/download-ticket'
import { folderFileUrl } from '../../api'

/**
 * 合同文件的「AI 审查」出口，诉讼页与非诉页共用。
 *
 * **整页编辑器（`?file=`）已删除**：它读 searchParams 却从来没有任何地方写入过
 * ——`FilePreview` 连同它带的逐条采纳 / 版本历史面板在生产里根本打不开，只能手改
 * URL 到达。而那些能力现在有正经入口：审查工作台（`/projects/:id/review/:taskId`）
 * 里有 `VersionChainPanel` 与逐条决策，画布本身则由 `DealDocLayout` 的「沉浸编辑」
 * 兜住「要更大」的需求。
 *
 * **为什么抽出来**：两页的文件夹来源相同（合同绑定目录）、传给审查抽屉的参数
 * 相同（当事人与立场依据）。各写一份必然漂移——之前非诉页接好了「AI 审查」而
 * 诉讼页根本没接，就是因为这段代码长在页面里。
 *
 * 页面负责持有状态（`reviewTarget` 由页面自己 useState），这里只负责渲染与跳转。
 * （编辑器框选的「划词」不再有对话框出口：选区直接进 AI 助手成引用卡，
 * 见 FilePreviewCard 的 onPluginMessage / copilot launch.ts 的 quoteCopilot。）
 */
export function ContractFileOverlays({
  ownerId,
  client,
  reviewTarget,
  onReviewClose,
}: {
  ownerId: number
  /** 委托人名称：作为「我方立场」的默认展示名 */
  client?: string
  /** 正在发起审查的文件；null = 不渲染 */
  reviewTarget: { subpath: string; name: string } | null
  onReviewClose: () => void
}) {
  const navigate = useNavigate()

  if (!reviewTarget) return null

  return (
    <ReviewLaunchDrawer
      open
      fileName={reviewTarget.name}
      loadFile={async () => {
        // 文件夹里的文件要带下载票据（浏览器原生请求带不上 Authorization 头）
        const url = await withDownloadTicket(folderFileUrl('contract', ownerId, reviewTarget.subpath))
        const res = await fetch(url)
        if (!res.ok) throw new Error('读取合同文件失败')
        return res.arrayBuffer()
      }}
      /**
       * 不再硬塞 {party_a: client, party_b: other}：那等于断定我方是甲方。
       * 当事人以抽屉内「上传后 AI 识别结果」为准，这里只传委托客户名，
       * 用于自动推荐我方是哪一方（识别不出就让律师自己选）。
       */
      clientName={client}
      partyHint={
        client
          ? `AI 依据：委托客户是「${client}」，若合同里有同名一方会自动选中；如判断有误请改。`
          : undefined
      }
      onClose={onReviewClose}
      onStarted={(taskId) => {
        onReviewClose()
        void navigate(projectReview(ownerId, taskId))
      }}
    />
  )
}
