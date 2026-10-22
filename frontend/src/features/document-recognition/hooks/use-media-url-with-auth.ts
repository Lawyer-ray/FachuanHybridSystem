import { useEffect, useState } from 'react'

import { resolveMediaUrlWithAuth } from '../domain'

/**
 * 带下载票据的 media URL（安全审计 M-2）。
 *
 * `<img src>` / `<iframe src>` 不能带 Authorization 头，而后端已不接受
 * `?token=<JWT>`（JWT 会进 access log / Referer）。改为：先用一次能带头的
 * 请求换 60 秒一次性票据，再拼进 URL。
 *
 * 票据是**一次性 + 短时**的，所以这里按 mediaUrl 变化重新取，不做长期缓存；
 * 组件卸载或 url 变化时丢弃旧旧票据（后端 TTL 自然过期）。
 */
export interface MediaUrlState {
  url: string
  /** 换票失败：调用方应展示可重试/新窗口打开的降级 UI，而不是留空白框 */
  failed: boolean
}

export function useMediaUrlWithAuth(mediaUrl: string | null | undefined): MediaUrlState {
  const [state, setState] = useState<MediaUrlState>({ url: '', failed: false })

  useEffect(() => {
    if (!mediaUrl) {
      setState({ url: '', failed: false })
      return
    }
    let alive = true
    // resolveMediaUrlWithAuth 内部换票失败会把原 path 原样返回（不带 ticket），
    // 此时直接塞进 iframe 只会得到一个 403 的空白框且永远转圈——标记出来，
    // 让调用方降级成「打开失败，点此新窗口打开」
    resolveMediaUrlWithAuth(mediaUrl)
      .then((next) => {
        if (!alive) return
        const failed = !next || !next.includes('ticket=')
        setState({ url: next, failed })
      })
      .catch(() => {
        if (alive) setState({ url: '', failed: true })
      })
    return () => {
      alive = false
    }
  }, [mediaUrl])

  return state
}
