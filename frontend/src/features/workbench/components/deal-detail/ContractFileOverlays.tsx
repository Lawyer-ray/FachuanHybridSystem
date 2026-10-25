import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { ReviewLaunchDrawer } from '@/features/contract-review'
import { withDownloadTicket } from '@/lib/download-ticket'
import { folderFileUrl } from '../../api'
import { FilePreview } from './FilePreview'

/**
 * 合同文件的「AI 审查」与「整页编辑」两个出口，诉讼页与非诉页共用。
 *
 * **为什么抽出来**：两页的文件夹来源相同（合同绑定目录）、传给审查抽屉的参数
 * 相同（当事人与立场依据）、整页编辑器也相同。各写一份必然漂移——之前非诉页
 * 接好了「AI 审查」而诉讼页根本没接，就是因为这段代码长在页面里。
 *
 * 页面负责持有状态（`reviewTarget` 由页面自己 useState），这里只负责渲染与跳转。
 */
export function ContractFileOverlays({
  ownerId,
  client,
  other,
  reviewTarget,
  onReviewClose,
  onReviewStart,
}: {
  ownerId: number
  /** 委托人名称：作为「我方立场」的默认展示名 */
  client?: string
  /** 对方当事人 */
  other?: string
  /** 正在发起审查的文件；null = 不渲染 */
  reviewTarget: { subpath: string; name: string } | null
  onReviewClose: () => void
  /**
   * 整页编辑器里点「AI 审查」时，把文件交回页面的 reviewTarget 状态。
   *
   * 做成 prop 而不是模块级回调：模块级可变状态在 SSR / 多实例（两页同时挂载、
   * 测试并行）下会互相覆盖，且违反 React 数据流（谁改的、什么时候改的看不出来）。
   */
  onReviewStart: (f: { subpath: string; name: string }) => void
}) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  /** `?file=` 存在时整页显示编辑器（可改可存）；否则不渲染 */
  const editing = useMemo(() => {
    const subpath = searchParams.get('file')
    if (!subpath) return null
    const mtimeRaw = searchParams.get('mtime')
    return {
      subpath,
      name: subpath.split('/').pop() || subpath,
      mtime: mtimeRaw ? Number(mtimeRaw) : undefined,
    }
  }, [searchParams])

  const closeEditor = () => {
    const next = new URLSearchParams(searchParams)
    next.delete('file')
    next.delete('mtime')
    // replace：关编辑器不该在历史里多压一条（后退应退出项目页而不是弹回来）
    setSearchParams(next, { replace: true })
  }

  if (editing) {
    return (
      <FilePreview
        kind="contract"
        ownerId={ownerId}
        file={editing}
        onBack={closeEditor}
        onReview={(f) => {
          closeEditor()
          onReviewStart(f)
        }}
        onSaved={() => {
          // 保存后让文件列表重取（大小与 mtime 变了）
          window.dispatchEvent(new CustomEvent('fachuan:folder-changed', { detail: { ownerId } }))
        }}
      />
    )
  }

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
      parties={{ party_a: client ?? '', party_b: other ?? '' }}
      partyHint={`AI 依据：合同抬头与历史来稿都指向「${client ?? ''}」为我方委托，如判断有误请改。`}
      onClose={onReviewClose}
      onStarted={(taskId) => {
        onReviewClose()
        void navigate(`/projects/${ownerId}/review/${taskId}`)
      }}
    />
  )
}
