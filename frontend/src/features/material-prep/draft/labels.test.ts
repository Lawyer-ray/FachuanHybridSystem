import type { DraftState } from '../types'
import { countUnclassified, isWholeMat, matLabel, segMats, selKeyOf } from './labels'

const mats = [
  { partIndex: 0, n: '起诉状.pdf', k: 'pdf' as const, pages: 3, customName: '自定义名.pdf' },
  { partIndex: 1, n: '证据.pdf', k: 'pdf' as const, pages: 2 },
]

describe('matLabel 三级回落', () => {
  it('自定义名 > 源文件名 > 兜底序号', () => {
    expect(matLabel(mats, 0)).toBe('自定义名.pdf')
    expect(matLabel(mats, 1)).toBe('证据.pdf')
    expect(matLabel(mats, 9)).toBe('材料 10')
    expect(matLabel([], 0)).toBe('材料 1')
  })
})

describe('segMats / selKeyOf', () => {
  it('segMats 去重返回涉及源；selKeyOf 拼 mi:p', () => {
    expect(segMats({ t: '', fn: 'x', manual: true, refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 1, p: 1 }] })).toEqual([0, 1])
    expect(segMats({ t: '', fn: 'x', manual: false, refs: [] })).toEqual([])
    expect(selKeyOf({ mi: 3, p: 12 })).toBe('3:12')
  })
})

describe('countUnclassified', () => {
  it('只数类型为空的段', () => {
    const d: DraftState = {
      mats,
      segs: [
        { t: '', fn: 'a.pdf', refs: [{ mi: 0, p: 1 }], manual: false },
        { t: '证据', fn: 'b.pdf', refs: [{ mi: 0, p: 2 }], manual: false },
        { t: '', fn: 'c.pdf', refs: [{ mi: 1, p: 1 }], manual: true },
      ],
      infos: [],
    }
    expect(countUnclassified(d)).toBe(2)
  })
})

describe('isWholeMat 整份判定', () => {
  function draft(segs: DraftState['segs']): DraftState {
    return { mats, segs, infos: [] }
  }

  it('单源且页集合与源文件完全相等才算整份', () => {
    const d = draft([
      { t: '起诉状', fn: '起诉状.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }], manual: false },
    ])
    expect(isWholeMat(d, 0)).toBe(true)
  })

  it('页数齐全但乱序 / 重复后仍相等（集合语义）', () => {
    const d = draft([
      { t: '', fn: 'x.pdf', refs: [{ mi: 0, p: 3 }, { mi: 0, p: 1 }, { mi: 0, p: 2 }], manual: false },
    ])
    expect(isWholeMat(d, 0)).toBe(true)
  })

  it('缺页、跨源段、越界段都不算整份', () => {
    const missing = draft([
      { t: '', fn: 'x.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }], manual: false },
    ])
    expect(isWholeMat(missing, 0)).toBe(false)

    const cross = draft([
      { t: '', fn: 'x.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }, { mi: 1, p: 1 }], manual: false },
    ])
    expect(isWholeMat(cross, 0)).toBe(false)

    const empty = draft([])
    expect(isWholeMat(empty, 0)).toBe(false)
  })
})
