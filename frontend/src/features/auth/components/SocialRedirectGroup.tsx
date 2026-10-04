/**
 * 登录页的跳转型社交登录按钮组。
 *
 * 与绑定页的 SocialRedirectPanel（单 Provider 面板 + 指引文案）不同：登录页把
 * 多个 redirect 型 Provider 与账密表单同页排成一行等宽小按钮（Cloudflare 式：
 * 图标 + 短名，provider 少于 4 个时不喧宾夺主）——共享一条「或使用以下方式登录」
 * 分割线与错误位。跳转进行中禁用全部按钮，避免连点双跳。
 */
import { useState } from 'react'
import type { SocialProviderInfo, SocialSession } from '../social-api'
import { socialAuthApi } from '../social-api'
import { BRAND_MARKS } from './brand-marks'

interface Props {
  providers: SocialProviderInfo[]
  /** 授权会话来源：默认登录 session（绑定页不走本组件） */
  createSession?: (provider: string) => Promise<SocialSession>
}

export function SocialRedirectGroup({ providers, createSession }: Props) {
  const [pendingName, setPendingName] = useState('')
  const [error, setError] = useState('')

  const start = async (provider: SocialProviderInfo) => {
    setPendingName(provider.name)
    setError('')
    try {
      const session = await (createSession ?? socialAuthApi.createSession)(provider.name)
      window.location.href = session.goto
    } catch (err) {
      setPendingName('')
      setError(err instanceof Error ? err.message : '该登录方式暂不可用，请稍后再试')
    }
  }

  return (
    <div className="fc-social">
      <p className="fc-social__divider" role="separator" aria-label="或使用以下方式登录">
        <span>或使用以下方式登录</span>
      </p>
      <div className="fc-social__buttons">
        {providers.map((provider) => {
          const Mark = BRAND_MARKS[provider.name]
          const pending = pendingName === provider.name
          return (
            <button
              key={provider.name}
              type="button"
              className={`fc-btn fc-btn--compact${Mark ? ' fc-btn--brand' : ''}`}
              disabled={pendingName !== ''}
              onClick={() => void start(provider)}
            >
              {pending ? (
                '跳转中…'
              ) : (
                <>
                  {Mark && <Mark />}
                  {provider.display_name || provider.name}
                </>
              )}
            </button>
          )
        })}
      </div>
      {error && <p className="fc-hint fc-hint--error">{error}</p>}
    </div>
  )
}
