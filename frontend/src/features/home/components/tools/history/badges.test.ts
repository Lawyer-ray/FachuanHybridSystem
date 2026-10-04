/**
 * home/tools/history/badges 单测（node 环境）：状态徽章配色查表 + 未知状态兜底。
 */
import { describe, expect, it } from 'vitest'

import { STATUS_BADGE, badgeOf } from './badges'

describe('badgeOf（状态徽章配色）', () => {
  it('已知状态逐一命中配色表（绿/红/黄/蓝语义）', () => {
    for (const status of Object.keys(STATUS_BADGE)) {
      expect(badgeOf(status)).toBe(STATUS_BADGE[status])
    }
    expect(badgeOf('completed')).toContain('status-green')
    expect(badgeOf('failed')).toContain('status-red')
    expect(badgeOf('pending')).toContain('status-yellow')
    expect(badgeOf('processing')).toContain('status-blue')
  })

  it('未知状态兜底为处理中蓝配色（不返回 undefined）', () => {
    expect(badgeOf('weird-status')).toBe(badgeOf('processing'))
    expect(typeof badgeOf('anything')).toBe('string')
  })
})
