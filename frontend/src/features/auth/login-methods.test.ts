import { describe, expect, it } from 'vitest'
import { PASSWORD_METHOD_ID, buildLoginMethods } from './login-methods'
import type { SocialProviderInfo } from './social-api'

function provider(over: Partial<SocialProviderInfo>): SocialProviderInfo {
  return {
    name: 'feishu',
    display_name: '飞书',
    login_mode: 'embedded_qr',
    client_config: null,
    ...over,
  }
}

describe('buildLoginMethods', () => {
  it('没有可用社交方式时只剩账号密码', () => {
    const methods = buildLoginMethods([])
    expect(methods).toHaveLength(1)
    expect(methods[0].id).toBe(PASSWORD_METHOD_ID)
    expect(methods[0].kind).toBe('password')
    expect(methods[0].provider).toBeNull()
  })

  it('账号密码永远排第一，Provider 按后端下发顺序跟在后头', () => {
    const methods = buildLoginMethods([
      provider({ name: 'feishu', display_name: '飞书' }),
      provider({ name: 'google', display_name: '谷歌', login_mode: 'redirect' }),
    ])
    expect(methods.map((m) => m.id)).toEqual([PASSWORD_METHOD_ID, 'feishu', 'google'])
  })

  it('按 login_mode 分派渲染形态', () => {
    const [, feishu, google] = buildLoginMethods([
      provider({ name: 'feishu', login_mode: 'embedded_qr' }),
      provider({ name: 'google', login_mode: 'redirect' }),
    ])
    expect(feishu?.kind).toBe('embedded_qr')
    expect(google?.kind).toBe('redirect')
  })

  it('未知 login_mode 一律按整页跳转处理，不让前端卡在没实现的形态上', () => {
    const [, unknown] = buildLoginMethods([provider({ login_mode: 'magic_link' as never })])
    expect(unknown?.kind).toBe('redirect')
  })

  it('display_name 缺失时回落 Provider 名，避免出现空白按钮', () => {
    const [, noName] = buildLoginMethods([provider({ name: 'wechat', display_name: '' })])
    expect(noName?.label).toBe('wechat')
  })

  it('Provider 原样挂在 method 上，供渲染器取 client_config', () => {
    const info = provider({ client_config: { width: '260' } })
    const [, method] = buildLoginMethods([info])
    expect(method?.provider).toBe(info)
  })
})
