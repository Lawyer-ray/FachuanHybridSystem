/**
 * 成本档位的纯函数测试。
 *
 * 这一层没有 UI，但错了同样看不见：档位与具体参数一旦对不上，用户点「经济」
 * 却拿到双引擎（多付一次云端费用），或者点「性能」却只跑了一种切法。
 * 所以逐个档位钉住**展开后的三项参数**，再钉住反解（`tierOf`）——反解错了，
 * 菜单会一边显示「标准」一边偷偷用着自定义参数。
 */
import { describe, expect, it } from 'vitest'

import { applyTier, costBadges, SPLIT_TIERS, tierOf } from './split-plan'

describe('applyTier：档位展开成具体参数', () => {
  it('经济 = 单引擎 + 分批 + 判定关', () => {
    expect(applyTier('cheap')).toEqual({ engines: ['mineru'], segmentStrategy: 'batch', judge: false })
  })

  it('标准 = 双引擎 + 分批 + 判定开（判定只在双引擎分歧上有事可做）', () => {
    expect(applyTier('standard')).toEqual({
      engines: ['mineru', 'paddleocr_vl'],
      segmentStrategy: 'batch',
      judge: true,
    })
  })

  it('性能 = 双引擎 + 两种切法都跑 + 判定开', () => {
    expect(applyTier('max')).toEqual({
      engines: ['mineru', 'paddleocr_vl'],
      segmentStrategy: 'wholebook_cross',
      judge: true,
    })
  })

  it('三档按成本从低到高排列（UI 直接按数组顺序渲染，顺序即语义）', () => {
    expect(SPLIT_TIERS.map((t) => t.id)).toEqual(['cheap', 'standard', 'max'])
    const costs = SPLIT_TIERS.map((t) => t.parseRuns + t.segmentRuns)
    expect(costs).toEqual([...costs].sort((a, b) => a - b))
  })
})

describe('tierOf：反解当前参数命中哪一档', () => {
  it('三档各自都能被反解命中', () => {
    for (const tier of SPLIT_TIERS) {
      expect(tierOf(applyTier(tier.id))).toBe(tier.id)
    }
  })

  it('改任何一项就变成自定义（null），不能继续显示成某档', () => {
    expect(tierOf({ engines: ['mineru', 'paddleocr_vl'], segmentStrategy: 'wholebook', judge: true })).toBeNull()
    expect(tierOf({ engines: ['mineru', 'paddleocr_vl'], segmentStrategy: 'batch', judge: false })).toBeNull()
    expect(tierOf({ engines: ['mineru'], segmentStrategy: 'batch', judge: true })).toBeNull()
  })

  it('单引擎 + 判定开 = 自定义（判定空转，不该被当成经济档）', () => {
    expect(tierOf({ engines: ['mineru'], segmentStrategy: 'batch', judge: true })).toBeNull()
  })

  it('容灾（一个引擎都不勾）+ 判定关 + 分批 也算经济档：结果参数与单引擎同价', () => {
    expect(tierOf({ engines: [], segmentStrategy: 'batch', judge: false })).toBe('cheap')
  })
})

describe('costBadges：两笔账分开写', () => {
  it('取字与分段各报各自的次数，不合成一个"倍数"', () => {
    const max = SPLIT_TIERS.find((t) => t.id === 'max')!
    expect(costBadges(max)).toBe('取字 2 遍 · 分段 2 遍')
    const cheap = SPLIT_TIERS.find((t) => t.id === 'cheap')!
    expect(costBadges(cheap)).toBe('取字 1 遍 · 分段 1 遍')
  })
})
