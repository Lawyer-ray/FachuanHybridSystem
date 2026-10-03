import { describe, expect, it } from 'vitest'

import { isLeaseFresh } from './api'

describe('isLeaseFresh（多 tab 刷新租约判定）', () => {
  it('新鲜租约：写入时间在窗口内视为有 tab 正在刷新', () => {
    expect(isLeaseFresh(String(1_000), 5_000)).toBe(true)
    expect(isLeaseFresh(String(1_000), 10_999)).toBe(true)
  })

  it('过期租约：达到/超过窗口视为持约 tab 已死，可自行刷新', () => {
    expect(isLeaseFresh(String(1_000), 11_000)).toBe(false)
    expect(isLeaseFresh(String(1_000), 60_000)).toBe(false)
  })

  it('null / 非数字 / 空串不新鲜', () => {
    expect(isLeaseFresh(null, 1_000)).toBe(false)
    expect(isLeaseFresh('abc', 1_000)).toBe(false)
    expect(isLeaseFresh('', 1_000)).toBe(false)
  })

  it('自定义窗口（maxAge）', () => {
    expect(isLeaseFresh(String(100), 150, 100)).toBe(true)
    expect(isLeaseFresh(String(100), 250, 100)).toBe(false)
  })
})
