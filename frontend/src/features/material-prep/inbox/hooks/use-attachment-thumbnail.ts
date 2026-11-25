import { useEffect, useState } from 'react'

import { fetchAttachmentThumbnail } from '../api'

export type ThumbnailState = 'idle' | 'loading' | 'ready' | 'failed'

/**
 * 附件的首页缩略图（object URL）。
 *
 * ## 为什么是 blob 而不是 `<img src="/api/...">`
 *
 * 见 `api.ts` 的 `fetchAttachmentThumbnail`：带鉴权的请求才能拿到字节，而票据
 * 方案会让 URL 每次都变、浏览器缓存永不命中。
 *
 * ## 为什么要 object URL 生命周期管理
 *
 * `URL.createObjectURL` 造出来的是**文档级**引用，不 revoke 就一直占内存——收件箱
 * 一屏几十张小图，反复展开/收起会稳定泄漏。这里在 effect 清理时 revoke，并在
 * 卸载后丢弃迟到的响应（否则会把已 revoke 的 URL 塞回 state，图片变成破图）。
 *
 * ## 为什么不做跨组件共享缓存
 *
 * 后端已给 `Cache-Control: private, max-age=604800`，同一 URL 的第二次 GET 由
 * 浏览器 HTTP 缓存直接命中（无网络、无票据）。再加一层进程内缓存只会多一份
 * 「谁负责 revoke」的复杂度。
 */
export function useAttachmentThumbnail(
  messageId: number,
  partIndex: number,
  opts: { page?: number; width?: number; enabled?: boolean } = {},
): { url: string | null; state: ThumbnailState } {
  const page = opts.page ?? 1
  const width = opts.width ?? 320
  const enabled = opts.enabled ?? true

  const [url, setUrl] = useState<string | null>(null)
  const [state, setState] = useState<ThumbnailState>('idle')

  useEffect(() => {
    if (!enabled) {
      setUrl(null)
      setState('idle')
      return
    }

    let alive = true
    let objectUrl: string | null = null
    setState('loading')

    fetchAttachmentThumbnail(messageId, partIndex, { page, width })
      .then((blob) => {
        if (!alive) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
        setState('ready')
      })
      .catch(() => {
        if (!alive) return
        setUrl(null)
        setState('failed')
      })

    return () => {
      alive = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [messageId, partIndex, page, width, enabled])

  return { url, state }
}
