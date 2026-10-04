import type { DraftState } from '../types'
import {
  applyPageSelection,
  flatRefs,
  isSelectionContiguous,
  mergePagesIntoNew,
  pageIndexOf,
  removePages,
  splitOutPages,
} from './selection'

/**
 * 场景底稿：mi=0（起诉状.pdf 3 页）+ mi=1（证据.pdf 2 页），各一整段。
 * 扁平序 = [0/1, 0/2, 0/3, 1/1, 1/2]。
 */
function fixture(): DraftState {
  return {
    mats: [
      { partIndex: 0, n: '起诉状.pdf', k: 'pdf', pages: 3 },
      { partIndex: 1, n: '证据.pdf', k: 'pdf', pages: 2 },
    ],
    segs: [
      { id: 'seg-a', t: '起诉状', fn: '起诉状.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }], manual: false },
      { id: 'seg-b', t: '证据', fn: '证据.pdf', refs: [{ mi: 1, p: 1 }, { mi: 1, p: 2 }], manual: false },
    ],
    infos: [],
  }
}

describe('flatRefs / pageIndexOf', () => {
  it('按段依序展开为扁平页序，记录 (段下标, 段内下标)', () => {
    const flat = flatRefs(fixture())
    expect(flat.map((f) => `${f.si}:${f.k}:${f.ref.mi}/${f.ref.p}`)).toEqual([
      '0:0:0/1',
      '0:1:0/2',
      '0:2:0/3',
      '1:0:1/1',
      '1:1:1/2',
    ])
  })

  it('pageIndexOf 返回扁平序下标，找不到返回 -1', () => {
    const d = fixture()
    expect(pageIndexOf(d, 0, 1)).toBe(0)
    expect(pageIndexOf(d, 1, 1)).toBe(3)
    expect(pageIndexOf(d, 9, 1)).toBe(-1)
    expect(pageIndexOf(d, 0, 99)).toBe(-1)
  })
})

describe('isSelectionContiguous', () => {
  it('段内连续 / 跨段相邻（扁平序连续）都算连续', () => {
    const d = fixture()
    expect(isSelectionContiguous(d, [{ mi: 0, p: 1 }, { mi: 0, p: 2 }])).toBe(true)
    // 0/3 与 1/1 在扁平序上相邻，允许跨源
    expect(isSelectionContiguous(d, [{ mi: 0, p: 3 }, { mi: 1, p: 1 }])).toBe(true)
  })

  it('跳页、跨段断档、重复选择、空选、不存在的页都不算连续', () => {
    const d = fixture()
    expect(isSelectionContiguous(d, [])).toBe(false)
    expect(isSelectionContiguous(d, [{ mi: 0, p: 1 }, { mi: 0, p: 3 }])).toBe(false)
    expect(isSelectionContiguous(d, [{ mi: 0, p: 1 }, { mi: 1, p: 2 }])).toBe(false)
    // 不存在的页被剔除后长度对不上
    expect(isSelectionContiguous(d, [{ mi: 0, p: 1 }, { mi: 9, p: 1 }])).toBe(false)
  })
})

describe('splitOutPages', () => {
  it('中间切出一段：前后残段保留原类型/名，新段人工、名带起始页', () => {
    const d = splitOutPages(fixture(), [{ mi: 0, p: 2 }])
    expect(d.segs).toHaveLength(4)
    const [head, cut, tail, other] = d.segs
    expect(head).toMatchObject({ t: '起诉状', fn: '起诉状.pdf', refs: [{ mi: 0, p: 1 }], manual: false })
    expect(cut).toMatchObject({ t: '', fn: '起诉状-P2.pdf', manual: true })
    expect(cut!.refs).toEqual([{ mi: 0, p: 2 }])
    expect(tail).toMatchObject({ t: '起诉状', fn: '起诉状.pdf', refs: [{ mi: 0, p: 3 }], manual: false })
    expect(other).toMatchObject({ t: '证据', fn: '证据.pdf' })
  })

  it('从头切：无前残段；从尾切：无后残段', () => {
    const head = splitOutPages(fixture(), [{ mi: 0, p: 1 }])
    expect(head.segs).toHaveLength(3)
    expect(head.segs[0]!.fn).toBe('起诉状-P1.pdf')
    const tail = splitOutPages(fixture(), [{ mi: 0, p: 3 }])
    expect(tail.segs).toHaveLength(3)
    expect(tail.segs[1]!.refs).toEqual([{ mi: 0, p: 3 }])
  })

  it('整份材料（首尾覆盖全段）不切；不连续选择不切；空选不切', () => {
    const d = fixture()
    expect(splitOutPages(d, [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }])).toBe(d)
    expect(splitOutPages(d, [{ mi: 0, p: 1 }, { mi: 0, p: 3 }])).toBe(d)
    expect(splitOutPages(d, [])).toBe(d)
  })
})

describe('mergePagesIntoNew', () => {
  it('跨源合并：原段移除被选页（空段清掉），尾部追加人工跨源段', () => {
    const d = mergePagesIntoNew(fixture(), [{ mi: 0, p: 3 }, { mi: 1, p: 1 }])
    expect(d.segs).toHaveLength(3)
    expect(d.segs[0]!.refs).toEqual([{ mi: 0, p: 1 }, { mi: 0, p: 2 }])
    expect(d.segs[1]!.refs).toEqual([{ mi: 1, p: 2 }])
    const merged = d.segs[2]
    expect(merged).toMatchObject({ t: '', fn: '合并材料.pdf', manual: true })
    expect(merged!.refs).toEqual([{ mi: 0, p: 3 }, { mi: 1, p: 1 }])
  })

  it('取走整份材料后空段被清理', () => {
    const d = mergePagesIntoNew(fixture(), [{ mi: 1, p: 1 }, { mi: 1, p: 2 }])
    expect(d.segs).toHaveLength(2)
    expect(d.segs[1]!.fn).toBe('合并材料.pdf')
  })
})

describe('applyPageSelection 分发', () => {
  it('选中都在同一段 → 走切出逻辑', () => {
    const d = applyPageSelection(fixture(), [{ mi: 0, p: 2 }])
    expect(d.segs.some((sg) => sg.fn === '起诉状-P2.pdf')).toBe(true)
  })

  it('选中跨段 → 走跨源合并', () => {
    const d = applyPageSelection(fixture(), [{ mi: 0, p: 3 }, { mi: 1, p: 1 }])
    expect(d.segs.at(-1)).toMatchObject({ fn: '合并材料.pdf', manual: true })
  })

  it('空选或不存在的页 → 原引用返回', () => {
    const d = fixture()
    expect(applyPageSelection(d, [])).toBe(d)
    expect(applyPageSelection(d, [{ mi: 7, p: 1 }])).toBe(d)
  })
})

describe('removePages', () => {
  it('删页后空段清理，其余段内容保持不变', () => {
    const d = removePages(fixture(), [{ mi: 1, p: 1 }, { mi: 1, p: 2 }])
    expect(d.segs).toHaveLength(1)
    expect(d.segs[0]).toEqual(fixture().segs[0])
  })

  it('删中间页保留段；空选返回原引用', () => {
    const d0 = fixture()
    const d = removePages(d0, [{ mi: 0, p: 2 }])
    expect(d.segs[0]!.refs).toEqual([{ mi: 0, p: 1 }, { mi: 0, p: 3 }])
    expect(d.segs[1]!.refs).toEqual([{ mi: 1, p: 1 }, { mi: 1, p: 2 }])
    // 未命中的页：内容不变（实现总是重建段对象，不做引用保持）
    expect(removePages(d0, [{ mi: 9, p: 1 }]).segs).toEqual(d0.segs)
    expect(removePages(d0, [])).toBe(d0)
  })
})

/** ⌘ 乱序点选场景底稿：单个 5 页 PDF 一整段（扁平序 = P1..P5） */
function fivePageFixture(): DraftState {
  return {
    mats: [{ partIndex: 0, n: '合同.pdf', k: 'pdf', pages: 5 }],
    segs: [
      {
        id: 'seg-x',
        t: '合同',
        fn: '合同.pdf',
        refs: [1, 2, 3, 4, 5].map((p) => ({ mi: 0, p })),
        manual: false,
      },
    ],
    infos: [],
  }
}

describe('⌘ 乱序点选落段按文档序 normalize', () => {
  it('先点 P5 再点 P4 后切出：新段 refs 是文档序，命名起始页用文档序首项', () => {
    const d = splitOutPages(fivePageFixture(), [{ mi: 0, p: 5 }, { mi: 0, p: 4 }])
    // 从尾部切出：只剩头段 + 新段
    expect(d.segs).toHaveLength(2)
    expect(d.segs[1]!.refs).toEqual([{ mi: 0, p: 4 }, { mi: 0, p: 5 }])
    expect(d.segs[1]!.fn).toBe('合同-P4.pdf')
  })

  it('乱序跨段合并：合并段 refs 仍按文档扁平序', () => {
    const d = mergePagesIntoNew(fixture(), [{ mi: 1, p: 1 }, { mi: 0, p: 3 }])
    expect(d.segs.at(-1)!.refs).toEqual([{ mi: 0, p: 3 }, { mi: 1, p: 1 }])
  })

  it('applyPageSelection 全链路：乱序传入切出后段内页序不颠倒', () => {
    const d = applyPageSelection(fivePageFixture(), [{ mi: 0, p: 5 }, { mi: 0, p: 4 }])
    expect(d.segs[1]!.refs).toEqual([{ mi: 0, p: 4 }, { mi: 0, p: 5 }])
  })
})
