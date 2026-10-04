import { describe, expect, it } from 'vitest'
import { buildLoginMethodGroups, PASSWORD_METHOD_ID } from './login-methods'
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

describe('buildLoginMethodGroups', () => {
  it('没有可用社交方式时只剩账号密码，两组皆空', () => {
    const groups = buildLoginMethodGroups([])
    expect(groups.password.id).toBe(PASSWORD_METHOD_ID)
    expect(groups.password.kind).toBe('password')
    expect(groups.password.provider).toBeNull()
    expect(groups.redirectProviders).toEqual([])
    expect(groups.qrProviders).toEqual([])
  })

  it('按 login_mode 分组：扫码进 qrProviders，其余进 redirectProviders，组内保持后端下发顺序', () => {
    const groups = buildLoginMethodGroups([
      provider({ name: 'google', display_name: '谷歌', login_mode: 'redirect' }),
      provider({ name: 'feishu', display_name: '飞书' }),
      provider({ name: 'github', display_name: 'GitHub', login_mode: 'redirect' }),
    ])
    expect(groups.redirectProviders.map((m) => m.id)).toEqual(['google', 'github'])
    expect(groups.qrProviders.map((m) => m.id)).toEqual(['feishu'])
  })

  it('未知 login_mode 一律按整页跳转处理，不让前端卡在没实现的形态上', () => {
    const groups = buildLoginMethodGroups([provider({ login_mode: 'magic_link' as never })])
    expect(groups.redirectProviders).toHaveLength(1)
    expect(groups.qrProviders).toEqual([])
  })

  it('display_name 缺失时回落 Provider 名，避免出现空白按钮', () => {
    const groups = buildLoginMethodGroups([provider({ name: 'wechat', display_name: '', login_mode: 'redirect' })])
    expect(groups.redirectProviders[0]?.label).toBe('wechat')
  })

  it('Provider 原样挂在 method 上且类型非空，供渲染器取 client_config', () => {
    const info = provider({ client_config: { width: '260' } })
    const groups = buildLoginMethodGroups([info])
    expect(groups.qrProviders[0]?.provider).toBe(info)
  })
})
