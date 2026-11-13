import { describe, expect, it } from 'vitest'
import { isSingleSourceContiguous } from './use-assign-launch'

describe('isSingleSourceContiguous', () => {
  it('单素材连续 → 通过', () => {
    expect(isSingleSourceContiguous([{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }])).toBe(true)
  })
  it('跨素材（实测丢页场景）→ 拒绝', () => {
    const refs = [
      ...Array.from({ length: 10 }, (_, i) => ({ mi: 0, p: i + 1 })),
      ...Array.from({ length: 6 }, (_, i) => ({ mi: 1, p: i + 1 })),
    ]
    expect(isSingleSourceContiguous(refs)).toBe(false)
  })
  it('跳页 → 拒绝', () => {
    expect(isSingleSourceContiguous([{ mi: 0, p: 1 }, { mi: 0, p: 3 }])).toBe(false)
  })
  it('空 → 拒绝', () => {
    expect(isSingleSourceContiguous([])).toBe(false)
  })
})
