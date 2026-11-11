/**
 * home 对外出口单测（node 环境）。
 *
 * 出口的关键契约是「lazy 出口与导航预取共用同一个 import()」——两者共用
 * 才能保证浏览器模块缓存只下载一次；若各写各的 import，预取就白费了。
 *
 * 注意：`preloadHomePage()` 会拉整个首页 chunk（含 ToolDock 的弹窗全家桶），
 * 在并行跑全量用例时可能超过默认 5s，因此这里显式放宽超时。
 */
import { describe, expect, it } from 'vitest'

import { HomePageLazy, preloadHomePage } from './index'

describe('home index 出口', () => {
  it('HomePageLazy 是 lazy 组件', () => {
    expect((HomePageLazy as unknown as { $$typeof: symbol }).$$typeof).toBe(Symbol.for('react.lazy'))
  })

  it(
    '预取 loader 解析到具名导出 HomePage',
    async () => {
      const mod = await preloadHomePage()
      expect(typeof mod.HomePage).toBe('function')
    },
    60_000,
  )
})
