// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RAIL_MAX_WIDTH, RAIL_MIN_WIDTH, readRailWidth } from './use-rail-width'

describe('readRailWidth', () => {
  beforeEach(() => localStorage.clear())

  it('没存过 → null（由调用方给默认值）', () => {
    expect(readRailWidth()).toBeNull()
  })

  it('存档超上限 → 被 clamp 回上限', () => {
    localStorage.setItem('mp.rail.width', String(RAIL_MAX_WIDTH + 500))
    expect(readRailWidth()).toBe(RAIL_MAX_WIDTH)
  })

  it('存档低于下限 → 被 clamp 回下限', () => {
    localStorage.setItem('mp.rail.width', '10')
    expect(readRailWidth()).toBe(RAIL_MIN_WIDTH)
  })

  it('非法值 → null，不抛', () => {
    localStorage.setItem('mp.rail.width', 'abc')
    expect(readRailWidth()).toBeNull()
  })

  it('localStorage 抛错也不抛（隐私模式）', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied')
    })
    expect(readRailWidth()).toBeNull()
    spy.mockRestore()
  })
})
