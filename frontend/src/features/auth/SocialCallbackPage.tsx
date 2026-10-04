/**
 * 社交登录回调页 — 飞书/微信等授权后由后端 302 到此。
 *
 * 三种落点，由 query 参数区分：
 * - `code=<TempAuth>`：登录流程，用一次性码换 JWT 再跳 redirect
 * - `bound=<provider>`：绑定流程，用户已登录、没有码可换，带标记跳回绑定页
 * - `error=<code>`：失败，映射成可读文案
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { Loader2 } from 'lucide-react'
import { useAuth } from './store'
import { socialAuthApi } from './social-api'
import { SOCIAL_LOGIN_ERROR_TEXT } from './constants'
import { resolveCallbackError, sanitizeRedirect, withQuery } from './social-callback-domain'

export function SocialCallbackPage() {
  const navigate = useNavigate()
  const setUser = useAuth((s) => s.setUser)
  // 显式状态机：'loading' 处理中 / 'failed' 失败可重试。此前用「message 是否等于
  // 初值」派生失败态，改文案就会改变行为。
  const [status, setStatus] = useState<'loading' | 'failed'>('loading')
  const [message, setMessage] = useState('正在完成登录…')
  // 严格模式下 effect 会跑两次，避免重复兑换（TempAuth 只能用一次，第二次必然失败）
  const exchanged = useRef(false)

  const fail = (text: string) => {
    setStatus('failed')
    setMessage(text)
  }

  useEffect(() => {
    if (exchanged.current) return
    exchanged.current = true

    const params = new URLSearchParams(window.location.search)
    const error = params.get('error')
    const bound = params.get('bound')
    const code = params.get('code')
    const redirect = sanitizeRedirect(params.get('redirect'))

    if (error) {
      fail(resolveCallbackError(error))
      return
    }

    // 绑定流程：身份已在后端关联到当前用户，这里没有码要换，直接回落地页
    if (bound) {
      void navigate(withQuery(redirect, { bound }), { replace: true })
      return
    }

    if (!code) {
      fail(SOCIAL_LOGIN_ERROR_TEXT.missing_code)
      return
    }

    void (async () => {
      try {
        const res = await socialAuthApi.exchangeToken(code)
        if (!res.success) {
          fail(res.message || SOCIAL_LOGIN_ERROR_TEXT.exchange_failed)
          return
        }
        setUser({
          id: res.user_id ?? 0,
          username: res.username ?? '',
        })
        void navigate(redirect, { replace: true })
      } catch (err) {
        fail(err instanceof Error ? err.message : SOCIAL_LOGIN_ERROR_TEXT.exchange_failed)
      }
    })()
  }, [navigate, setUser])

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background px-4">
      {status === 'loading' && <Loader2 className="size-5 animate-spin text-muted-foreground" />}
      <p className="text-[13px] text-muted-foreground">{message}</p>
      {status === 'failed' && (
        <button
          type="button"
          onClick={() => { void navigate('/login', { replace: true }) }}
          className="text-xs text-primary underline-offset-4 hover:underline"
        >
          返回登录页
        </button>
      )}
    </div>
  )
}
