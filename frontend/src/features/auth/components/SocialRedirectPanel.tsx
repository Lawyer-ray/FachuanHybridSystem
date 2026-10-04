/**
 * 整页跳转型登录方式（redirect）的按钮面板。
 *
 * 与内嵌二维码相对：拿不到可渲染的二维码，只能整页导航到平台授权页，
 * 授权后由后端 302 回 /social-callback。绑定页一个面板只放一个 Provider，
 * 自带操作指引；登录页多 Provider 堆叠走 SocialRedirectGroup。
 */
import { useState } from 'react'
import type { SocialProviderInfo, SocialSession } from '../social-api'
import { socialAuthApi } from '../social-api'
import { spacedBrand } from '../social-format'
import { BRAND_MARKS } from './brand-marks'

interface Props {
  provider: SocialProviderInfo
  /** 授权会话来源：登录页用默认（登录 session），绑定页传 bind-session */
  createSession?: (provider: string) => Promise<SocialSession>
}

export function SocialRedirectPanel({ provider, createSession }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const start = async () => {
    setLoading(true)
    setError('')
    try {
      const session = await (createSession ?? socialAuthApi.createSession)(provider.name)
      window.location.href = session.goto
    } catch (err) {
      setLoading(false)
      setError(err instanceof Error ? err.message : '该登录方式暂不可用，请稍后再试')
    }
  }

  // 从模块级常量表取值（不是 render 里新建组件），引用稳定，不会触发重挂载
  const Mark = BRAND_MARKS[provider.name]

  return (
    <div className="fc-redirect">
      <button
        type="button"
        className={`fc-btn${Mark ? ' fc-btn--brand' : ''}`}
        disabled={loading}
        onClick={() => void start()}
      >
        {loading ? (
          '正在跳转…'
        ) : (
          <>
            {Mark && <Mark />}
            {spacedBrand('使用', provider.display_name, '登录')}
          </>
        )}
      </button>
      {error ? (
        <p className="fc-hint fc-hint--error">{error}</p>
      ) : (
        <p className="fc-hint">{spacedBrand('将跳转到', provider.display_name, '完成授权')}</p>
      )}
    </div>
  )
}
