import type { DraftState } from '../types'
import {
  countUnclassified,
  defaultSegName,
  isAutoSegName,
  isWholeMat,
  matLabel,
  segMats,
  segRangeText,
  selKeyOf,
  withDefaultNames,
} from './labels'

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
    expect(segMats({ id: 's1', t: '', fn: 'x', manual: true, refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 1, p: 1 }] })).toEqual([0, 1])
    expect(segMats({ id: 's2', t: '', fn: 'x', manual: false, refs: [] })).toEqual([])
    expect(selKeyOf({ mi: 3, p: 12 })).toBe('3:12')
  })
})

describe('countUnclassified', () => {
  it('只数类型为空的段', () => {
    const d: DraftState = {
      mats,
      segs: [
        { id: 's1', t: '', fn: 'a.pdf', refs: [{ mi: 0, p: 1 }], manual: false },
        { id: 's2', t: '证据', fn: 'b.pdf', refs: [{ mi: 0, p: 2 }], manual: false },
        { id: 's3', t: '', fn: 'c.pdf', refs: [{ mi: 1, p: 1 }], manual: true },
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
      { id: 's1', t: '起诉状', fn: '起诉状.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }], manual: false },
    ])
    expect(isWholeMat(d, 0)).toBe(true)
  })

  it('页数齐全但乱序 / 重复后仍相等（集合语义）', () => {
    const d = draft([
      { id: 's1', t: '', fn: 'x.pdf', refs: [{ mi: 0, p: 3 }, { mi: 0, p: 1 }, { mi: 0, p: 2 }], manual: false },
    ])
    expect(isWholeMat(d, 0)).toBe(true)
  })

  it('缺页、跨源段、越界段都不算整份', () => {
    const missing = draft([
      { id: 's1', t: '', fn: 'x.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }], manual: false },
    ])
    expect(isWholeMat(missing, 0)).toBe(false)

    const cross = draft([
      { id: 's1', t: '', fn: 'x.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }, { mi: 1, p: 1 }], manual: false },
    ])
    expect(isWholeMat(cross, 0)).toBe(false)

    const empty = draft([])
    expect(isWholeMat(empty, 0)).toBe(false)
  })
})

describe('defaultSegName / isAutoSegName 默认命名规则', () => {
  const d: DraftState = { mats, segs: [], infos: [] }

  it('整份 = 源标签（自定义名优先）；非整份 = 源名-P起始页.ext；跨源取首页所在源；空段兜底', () => {
    expect(defaultSegName(d, [{ mi: 0, p: 1 }], true)).toBe('自定义名.pdf')
    expect(defaultSegName(d, [{ mi: 0, p: 2 }, { mi: 0, p: 3 }], false)).toBe('自定义名-P2.pdf')
    expect(defaultSegName(d, [{ mi: 1, p: 2 }, { mi: 0, p: 1 }], false)).toBe('证据-P2.pdf')
    expect(defaultSegName(d, [], false)).toBe('材料.pdf')
  })

  it('源文件名本身与「源名-P数字.ext」算默认名，其它都是用户改过的', () => {
    expect(isAutoSegName(d, '证据.pdf')).toBe(true)
    expect(isAutoSegName(d, '证据-P3.pdf')).toBe(true)
    expect(isAutoSegName(d, '自定义名-P12.pdf')).toBe(true)
    expect(isAutoSegName(d, '证据-Px.pdf')).toBe(false)
    expect(isAutoSegName(d, '证据-P3.docx')).toBe(false)
    expect(isAutoSegName(d, '借条.pdf')).toBe(false)
    expect(isAutoSegName(d, '合并材料.pdf')).toBe(false)
  })
})

describe('withDefaultNames 刷新默认名', () => {
  it('仍用默认名的段按页区间重算，变回整份就变回源名；用户改过的名原样保留', () => {
    const d: DraftState = {
      mats,
      segs: [
        // 名字还是源名但已不是整份 → 带起始页
        { id: 'a', t: '', fn: '证据.pdf', refs: [{ mi: 1, p: 2 }], manual: true },
        // 带 -P 的默认名但起始页已变（首页被删） → 跟着变
        { id: 'b', t: '', fn: '自定义名-P1.pdf', refs: [{ mi: 0, p: 2 }, { mi: 0, p: 3 }], manual: true },
        // 用户改过的名不动
        { id: 'c', t: '', fn: '借条.pdf', refs: [{ mi: 0, p: 1 }], manual: true },
      ],
      infos: [],
    }
    const out = withDefaultNames(d)
    expect(out.segs.map((s) => s.fn)).toEqual(['证据-P2.pdf', '自定义名-P2.pdf', '借条.pdf'])

    const whole: DraftState = {
      mats,
      segs: [{ id: 'w', t: '', fn: '证据-P1.pdf', refs: [{ mi: 1, p: 1 }, { mi: 1, p: 2 }], manual: true }],
      infos: [],
    }
    expect(withDefaultNames(whole).segs[0]!.fn).toBe('证据.pdf')
  })

  it('无变化时返回原引用（update 可据此跳过重渲）', () => {
    const d: DraftState = {
      mats,
      segs: [{ id: 'a', t: '', fn: '证据.pdf', refs: [{ mi: 1, p: 1 }, { mi: 1, p: 2 }], manual: false }],
      infos: [],
    }
    expect(withDefaultNames(d)).toBe(d)
  })
})

describe('segRangeText 页区间文案', () => {
  const seg = (refs: DraftState['segs'][number]['refs']) => ({ id: 'x', t: '', fn: 'x', manual: true, refs })

  it('单源连续 P5–19；单页 P4；断续按段落列出；跨源只标「跨源」', () => {
    expect(segRangeText(seg(Array.from({ length: 15 }, (_, i) => ({ mi: 0, p: 5 + i }))))).toBe('P5–19')
    expect(segRangeText(seg([{ mi: 0, p: 4 }]))).toBe('P4')
    expect(segRangeText(seg([{ mi: 0, p: 3 }, { mi: 0, p: 7 }, { mi: 0, p: 8 }, { mi: 0, p: 9 }]))).toBe('P3, P7–9')
    expect(segRangeText(seg([{ mi: 0, p: 3 }, { mi: 1, p: 1 }]))).toBe('跨源')
    expect(segRangeText(seg([]))).toBe('')
  })
})
