/**
 * 跳转型社交登录的发起状态机。
 *
 * 两处消费方只有「谁能发起」与「pending 怎么呈现」不同，状态机本身逐字相同：
 * - 登录页 SocialRedirectGroup：多个 Provider 排成一行，只禁用被点的那一家的
 *   文案换成「跳转中…」，其余按钮整体禁用（防双跳）；
 * - 绑定页 SocialRedirectPanel：单个 Provider，pending 布尔化后整体禁用按钮。
 * 因此状态统一记成「正在跳转的 Provider 名」——面板把它布尔化即可，
 * 分叉只留在渲染层。成功路径必然整页导航走（window.location.href），
 * 不会复位 pending：页面已经要走了。
 */
import { useState } from 'react'

import { errMessage } from '@/lib/errors'
import { SOCIAL_REDIRECT_FAIL_TEXT } from '../constants'
import { socialAuthApi } from '../social-api'
import type { SocialSession } from '../types'

/** 授权会话来源：默认登录 session（登录页），绑定页传 bind-session */
export type CreateSession = (provider: string) => Promise<SocialSession>

export function useSocialRedirect(createSession?: CreateSession) {
  const [pendingName, setPendingName] = useState('')
  const [error, setError] = useState('')

  const start = async (providerName: string) => {
    setPendingName(providerName)
    setError('')
    try {
      const session = await (createSession ?? socialAuthApi.createSession)(providerName)
      window.location.href = session.goto
    } catch (err) {
      setPendingName('')
      setError(errMessage(err, SOCIAL_REDIRECT_FAIL_TEXT))
    }
  }

  return { pendingName, error, start }
}
