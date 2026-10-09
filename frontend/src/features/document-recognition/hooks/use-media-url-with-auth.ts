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
 * 组件卸载或 url 变化时丢弃旧票据（后端 TTL 自然过期）。
 */
export function useMediaUrlWithAuth(mediaUrl: string | null | undefined): string {
  const [url, setUrl] = useState('')

  useEffect(() => {
    if (!mediaUrl) {
      setUrl('')
      return
    }
    let alive = true
    void resolveMediaUrlWithAuth(mediaUrl).then((next) => {
      if (alive) setUrl(next)
    })
    return () => {
      alive = false
    }
  }, [mediaUrl])

  return url
}
