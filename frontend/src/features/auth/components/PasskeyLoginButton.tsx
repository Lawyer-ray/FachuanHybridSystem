/**
 * 登录页的「通行密钥」一键登录按钮。
 *
 * 放在密码表单与社交登录按钮之间：它是本系统最顺手的登录方式（Touch ID /
 * Windows Hello 一按即入），但依赖「本域已注册过密钥」，所以视觉上是次级
 * 按钮而非主表单。浏览器不支持 WebAuthn 或没有平台认证器时整块不渲染。
 *
 * 流程：login/options → navigator.credentials.get（系统弹出 Touch ID）→
 * login/verify（token 已在 API 层落 localStorage）→ 补 zustand 用户态 →
 * 进首页。与社交登录不同，全程同页完成，无需 /social-callback 中转。
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { useAuth } from '../store'
import { passkeyApi } from '../passkey-api'
import { credentialToAssertionJSON, toRequestOptions } from '../passkey-coding'

/** WebAuthn + 平台认证器（Touch ID / Windows Hello）双条件可用才展示入口 */
async function platformAuthenticatorAvailable(): Promise<boolean> {
  if (typeof window === 'undefined' || !window.PublicKeyCredential) return false
  try {
    return await window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()
  } catch {
    return false
  }
}

export function PasskeyLoginButton() {
  const navigate = useNavigate()
  const setUser = useAuth((state) => state.setUser)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [available, setAvailable] = useState(false)

  useEffect(() => {
    let mounted = true
    void platformAuthenticatorAvailable().then((ok) => {
      if (mounted) setAvailable(ok)
    })
    return () => {
      mounted = false
    }
  }, [])

  if (!available) return null

  const login = async () => {
    setPending(true)
    setError('')
    try {
      const options = await passkeyApi.loginOptions()
      const credential = await navigator.credentials.get(toRequestOptions(options))
      if (!credential) throw new Error('未找到匹配的通行密钥')
      const result = await passkeyApi.loginVerify(
        credentialToAssertionJSON(credential as unknown as Parameters<typeof credentialToAssertionJSON>[0]),
      )
      if (!result.success || !result.access || !result.refresh) {
        throw new Error(result.message || '通行密钥登录失败')
      }
      setUser({ id: result.user_id ?? 0, username: result.username })
      void navigate('/', { replace: true })
    } catch (err) {
      setPending(false)
      // NotAllowedError 同时覆盖「用户取消」与「本设备无本域密钥」：
      // 取消是静默常态，这里统一给指引文案（注册入口在账号绑定页）
      if (err instanceof DOMException && err.name === 'NotAllowedError') {
        setError('未验证通行密钥。请先用密码登录，再在「账号绑定」中添加本设备的通行密钥')
        return
      }
      setError(err instanceof Error ? err.message : '通行密钥登录失败，请稍后再试')
    }
  }

  return (
    <div className="mt-4 flex flex-col items-center gap-2">
      <button
        type="button"
        className="fc-btn fc-btn--ghost w-full"
        disabled={pending}
        onClick={() => void login()}
      >
        {pending ? '等待验证…' : '使用通行密钥登录'}
      </button>
      {error && <p className="fc-hint fc-hint--error">{error}</p>}
    </div>
  )
}
