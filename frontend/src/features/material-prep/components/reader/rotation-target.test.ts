/**
 * 「转正」按钮的作用范围（node 环境）。
 *
 * 这是本次唯一会**批量改 37 页方向**的入口，作用范围算错的后果比单页按钮大得多：
 * 律师以为在转「这一份」，实际把整包都翻了。所以按优先级与标签逐条钉死。
 */
import { describe, expect, it } from 'vitest'

import type { DraftState } from '../../types'
import { rotationTargetOf } from './rotation-target'

const mats = [
  { partIndex: 0, n: 'a.pdf', k: 'pdf', pages: 3 },
  { partIndex: 5, n: 'b.pdf', k: 'pdf', pages: 2 },
] as const

function draft(over: Partial<DraftState> = {}): DraftState {
  return {
    mats: mats as never,
    segs: [
      { id: 's1', t: '', fn: '第一份', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }], manual: false },
      { id: 's2', t: '', fn: '第二份', refs: [{ mi: 1, p: 1 }], manual: false },
    ],
    infos: [],
    ...over,
  } as DraftState
}

describe('rotationTargetOf', () => {
  it('有选中页时只作用于所选', () => {
    const t = rotationTargetOf(draft(), [{ mi: 0, p: 2 }, { mi: 1, p: 2 }], 0)
    expect(t.refs).toEqual([{ mi: 0, p: 2 }, { mi: 1, p: 2 }])
    expect(t.label).toBe('所选 2 页')
  })

  it('没选中时作用于当前段（这是「这一份材料」的粒度）', () => {
    const t = rotationTargetOf(draft(), [], 1)
    expect(t.refs).toEqual([{ mi: 1, p: 1 }])
    expect(t.label).toBe('当前段 1 页')
  })

  it('没有段（还没分段）时兜底到全部页', () => {
    const t = rotationTargetOf(draft({ segs: [] }), [], 0)
    expect(t.refs).toHaveLength(5) // 3 + 2
    expect(t.label).toBe('全部 5 页')
  })

  it('已转正页数按 partIndex 换算后统计（选中页里有转过 2 页）', () => {
    const t = rotationTargetOf(
      draft({ pageRot: { '0:1': 90, '5:1': 180 } }),
      [{ mi: 0, p: 1 }, { mi: 1, p: 1 }, { mi: 0, p: 3 }],
      0,
    )
    expect(t.rotatedCount).toBe(2)
  })

  it('没有草稿时不给出可点目标（按钮置灰而不是静默转错）', () => {
    const t = rotationTargetOf(null, [], 0)
    expect(t.refs).toEqual([])
    expect(t.label).toBe('没有可转的页')
  })
})
