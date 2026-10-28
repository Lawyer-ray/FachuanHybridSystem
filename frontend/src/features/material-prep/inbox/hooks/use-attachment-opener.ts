import { useCallback, useState } from 'react'
import { toast } from 'sonner'

import { downloadUrl } from '@/lib/download'
import { withDownloadTicket } from '@/lib/download-ticket'
import { errMessage } from '@/lib/errors'
import { attachmentUrl } from '../api'

/** 正在换票的附件（用于按钮转圈 + 防重复点击） */
export interface PendingAttachment {
  partIndex: number
  kind: 'preview' | 'download'
}

/**
 * 附件预览 / 下载。
 *
 * **为什么不能直接用 `<a href>`**（这曾是一个真实 bug）：
 *
 * 本应用的 JWT 存在 localStorage，只有经 ky 发出的请求才带 `Authorization`
 * 头；普通 `<a href>` 是浏览器导航，带不上它。后端 `JWTOrSessionAuth` 也
 * **刻意不收** `?token=<JWT>`——安全审计 2026Q4 M-2：完整 JWT 会落进 nginx
 * access log、浏览器历史、Referer 与中间代理日志，拿到即等于拿到身份。
 *
 * 于是 `<a href="/api/v1/inbox/.../preview">` 在任何账号下都得到 401，
 * 与「有没有权限看这条消息」无关——这就是「用自己的账号下载自己的一张网
 * 材料也失败」的原因，它从来不是权限问题。
 *
 * 正确路径是后端为这类场景准备的**短时一次性下载票据**：已认证端点
 * `POST /download-ticket` 换 `?ticket=`（票据只含 user_id、默认 60 秒、单次
 * 使用），再当普通链接打开。办案模块的文档预览/下载一直这么走
 * （`lib/download-ticket` + `lib/download`），收件箱抽屉当初没接上这套。
 *
 * 票据单次使用，因此每次点击都现换、不复用；换票失败时 `withDownloadTicket`
 * 会原样返回 URL，由后端按 403 拒绝——比前端静默改掉 href 更好定位。
 */
export function useAttachmentOpener(messageId: number): {
  pending: PendingAttachment | null
  run: (partIndex: number, kind: 'preview' | 'download') => Promise<void>
} {
  const [pending, setPending] = useState<PendingAttachment | null>(null)

  const run = useCallback(
    async (partIndex: number, kind: 'preview' | 'download') => {
      setPending({ partIndex, kind })
      try {
        const url = attachmentUrl(messageId, partIndex, kind === 'preview')
        const signed = await withDownloadTicket(url)
        if (kind === 'preview') {
          // 预览开新标签：后端 preview 端点响应是 inline，浏览器直接渲染 PDF/图片。
          // noopener 必须给——否则新页能拿 window.opener 反控本页。
          window.open(signed, '_blank', 'noopener,noreferrer')
        } else {
          // 下载交给 Content-Disposition 决定文件名（后端已按原名/自定义名重命名好）
          downloadUrl(signed)
        }
      } catch (e) {
        toast.error(errMessage(e, kind === 'preview' ? '预览失败' : '下载失败'))
      } finally {
        setPending(null)
      }
    },
    [messageId],
  )

  return { pending, run }
}
