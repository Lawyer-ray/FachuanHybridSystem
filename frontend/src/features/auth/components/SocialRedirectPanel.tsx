/**
 * 整页跳转型登录方式（redirect）的按钮面板。
 *
 * 与内嵌二维码相对：拿不到可渲染的二维码，只能整页导航到平台授权页，
 * 授权后由后端 302 回 /social-callback。谷歌网页登录等后续方式走这条路。
 */
import { useState, type ComponentType } from 'react'
import type { SocialProviderInfo, SocialSession } from '../social-api'
import { socialAuthApi } from '../social-api'
import { spacedBrand } from '../social-format'
import { GitHubIcon } from './GitHubIcon'
import { GoogleIcon } from './GoogleIcon'

/**
 * 品牌标注册表。
 *
 * 有标的 Provider 走浅底样式：彩色 logo 落在登录页的黄铜底上不可辨（Google 黄
 * 对比度仅约 1.3:1），只能配白底——这也正是 Google 品牌规范要求的用法。
 * 没有标的（飞书）沿用黄铜主按钮，外观与改动前完全一致。新增平台加一行即可。
 */
const BRAND_MARKS: Record<string, ComponentType<{ size?: number }>> = {
  google: GoogleIcon,
  github: GitHubIcon,
}

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
