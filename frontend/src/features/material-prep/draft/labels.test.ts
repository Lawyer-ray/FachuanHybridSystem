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

  it('选了类型 → 「类型.pdf」，同类型已有一份 → 「类型-P起始页.pdf」（used 集合去重）', () => {
    expect(defaultSegName(d, [{ mi: 0, p: 1 }], false, '借条')).toBe('借条.pdf')
    expect(defaultSegName(d, [{ mi: 0, p: 3 }], false, '借条', new Set(['借条.pdf']))).toBe('借条-P3.pdf')
  })

  it('默认名判定：源文件名本身与「源名-P数字.ext」算默认名，其它都是用户改过的', () => {
    const noType = { fn: '', t: '' }
    expect(isAutoSegName(d, { ...noType, fn: '证据.pdf' })).toBe(true)
    expect(isAutoSegName(d, { ...noType, fn: '证据-P3.pdf' })).toBe(true)
    expect(isAutoSegName(d, { ...noType, fn: '自定义名-P12.pdf' })).toBe(true)
    expect(isAutoSegName(d, { ...noType, fn: '证据-Px.pdf' })).toBe(false)
    expect(isAutoSegName(d, { ...noType, fn: '证据-P3.docx' })).toBe(false)
    // 手动改成一个类型名（但该段没选这个类型）→ 当作用户名保留
    expect(isAutoSegName(d, { ...noType, fn: '借条.pdf' })).toBe(false)
    expect(isAutoSegName(d, { ...noType, fn: '合并材料.pdf' })).toBe(false)
  })

  it('该段自己的类型名算默认名；fnAuto 是唯一可靠来源', () => {
    expect(isAutoSegName(d, { fn: '借条.pdf', t: '借条' })).toBe(true)
    expect(isAutoSegName(d, { fn: '借条-P3.pdf', t: '借条' })).toBe(true)
    // 名字像别的类型的默认名 ≠ 自己的默认名
    expect(isAutoSegName(d, { fn: '借条.pdf', t: '银行流水' })).toBe(false)
    // 有 fnAuto 只看 fn 是否等于它
    expect(isAutoSegName(d, { fn: '随便起的名字', t: '', fnAuto: '随便起的名字' })).toBe(true)
    expect(isAutoSegName(d, { fn: '借条.pdf', t: '借条', fnAuto: '起诉状.pdf' })).toBe(false)
  })
})

describe('withDefaultNames 刷新默认名', () => {
  it('仍用默认名的段按页区间 / 类型重算，变回整份就变回源名；用户改过的名原样保留', () => {
    const d: DraftState = {
      mats,
      segs: [
        // 名字还是源名但已不是整份 → 带起始页
        { id: 'a', t: '', fn: '证据.pdf', refs: [{ mi: 1, p: 2 }], manual: true },
        // 带 -P 的默认名但起始页已变（首页被删） → 跟着变
        { id: 'b', t: '', fn: '自定义名-P1.pdf', refs: [{ mi: 0, p: 2 }, { mi: 0, p: 3 }], manual: true },
        // 用户改过的名不动（「借条.pdf」不是该段的类型默认名，且无 fnAuto → 按模式判定为用户名）
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

  it('选类型后名字跟类型走；同类型第二份加 -P；fnAuto 记录来源，改名后再换类型不再跟随', () => {
    const d: DraftState = {
      mats,
      segs: [
        { id: 'a', t: '', fn: '证据.pdf', refs: [{ mi: 1, p: 1 }, { mi: 1, p: 2 }], manual: true },
        { id: 'b', t: '', fn: '自定义名-P1.pdf', refs: [{ mi: 0, p: 2 }], manual: true },
      ],
      infos: [],
    }
    const typed = withDefaultNames({ ...d, segs: [{ ...d.segs[0]!, t: '借条' }, { ...d.segs[1]!, t: '借条' }] })
    // 第一份「借条.pdf」，第二份同类型 → 「借条-P2.pdf」；并记录 fnAuto
    expect(typed.segs.map((s) => [s.fn, s.fnAuto])).toEqual([
      ['借条.pdf', '借条.pdf'],
      ['借条-P2.pdf', '借条-P2.pdf'],
    ])

    // fn !== fnAuto（用户手改）之后类型再变，名字不再跟随
    const renamed = withDefaultNames({ ...typed, segs: [{ ...typed.segs[0]!, fn: '客户原件.pdf' }] })
    expect(renamed.segs[0]!.fn).toBe('客户原件.pdf')
  })

  it('首刷为老草稿补 fnAuto（对象会换）；之后 fn 不变时返回同一引用', () => {
    const d: DraftState = {
      mats,
      segs: [{ id: 'a', t: '', fn: '证据.pdf', refs: [{ mi: 1, p: 1 }, { mi: 1, p: 2 }], manual: false }],
      infos: [],
    }
    const first = withDefaultNames(d)
    // fn 没变，但补上了 fnAuto 来源记录
    expect(first.segs[0]!.fn).toBe('证据.pdf')
    expect(first.segs[0]!.fnAuto).toBe('证据.pdf')
    expect(withDefaultNames(first)).toBe(first)
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
