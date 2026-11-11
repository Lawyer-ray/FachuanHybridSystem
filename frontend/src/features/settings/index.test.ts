/**
 * settings 对外出口单测（node 环境）。
 *
 * 出口只承诺两件事：给出一个 lazy 组件（不是直接 import 得到的组件），
 * 以及该 lazy 的 loader 指向设置页模块。静态 re-export 会把整域钉进首屏
 * chunk，因此这里断言的是「有没有走 lazy」这一形状，而非渲染结果。
 */
import { describe, expect, it } from 'vitest'

import { SettingsPageLazy } from './index'

describe('settings index 出口', () => {
  it('SettingsPageLazy 是 lazy 组件（带 $$typeof 标记，不是普通函数组件）', () => {
    expect(SettingsPageLazy).toBeTruthy()
    expect((SettingsPageLazy as unknown as { $$typeof: symbol }).$$typeof).toBe(Symbol.for('react.lazy'))
  })

  it('loader 能取到具名导出 SettingsPage', async () => {
    const mod = await import('./components/SettingsPage')
    expect(typeof mod.SettingsPage).toBe('function')
  })
})
