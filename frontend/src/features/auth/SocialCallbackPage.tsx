/**
 * 社交登录回调页 — 飞书/微信等授权后由后端 302 到此。
 *
 * URL 形如 /social-callback?code=<TempAuth>&redirect=/material-prep
 * 其中 code 是一次性 UUID（不是 Provider 授权码，那个已在后端回调时用过并作废）。
 * 这里用它在 /token-exchange 换 JWT，然后跳 redirect。
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { Loader2 } from 'lucide-react'
import { useAuth } from './store'
import { socialAuthApi } from './social-api'
import { SOCIAL_LOGIN_ERROR_TEXT } from './social-types'
import { resolveCallbackError, sanitizeRedirect } from './social-callback-domain'

export function SocialCallbackPage() {
  const navigate = useNavigate()
  const setUser = useAuth((s) => s.setUser)
  const [message, setMessage] = useState('正在完成登录…')
  // 严格模式下 effect 会跑两次，避免重复兑换（TempAuth 只能用一次，第二次必然失败）
  const exchanged = useRef(false)

  useEffect(() => {
    if (exchanged.current) return
    exchanged.current = true

    const params = new URLSearchParams(window.location.search)
    const error = params.get('error')
    const code = params.get('code')
    const redirect = sanitizeRedirect(params.get('redirect'))

    if (error) {
      setMessage(resolveCallbackError(error))
      return
    }
    if (!code) {
      setMessage(SOCIAL_LOGIN_ERROR_TEXT.missing_code)
      return
    }

    void (async () => {
      try {
        const res = await socialAuthApi.exchangeToken(code)
        if (!res.success) {
          setMessage(res.message || SOCIAL_LOGIN_ERROR_TEXT.exchange_failed)
          return
        }
        setUser({
          id: res.user_id ?? 0,
          username: res.username ?? '',
        })
        navigate(redirect, { replace: true })
      } catch (err) {
        setMessage(err instanceof Error ? err.message : SOCIAL_LOGIN_ERROR_TEXT.exchange_failed)
      }
    })()
  }, [navigate, setUser])

  const failed = message !== '正在完成登录…'

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background px-4">
      {!failed && <Loader2 className="size-5 animate-spin text-muted-foreground" />}
      <p className="text-[13px] text-muted-foreground">{message}</p>
      {failed && (
        <button
          type="button"
          onClick={() => navigate('/login', { replace: true })}
          className="text-xs text-primary underline-offset-4 hover:underline"
        >
          返回登录页
        </button>
      )}
    </div>
  )
}
