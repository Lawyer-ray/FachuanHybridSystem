import type { DraftState, PdfSplitSegmentSuggestion } from '../types'
import { applyAutoSplit, canAutoSplitMat, renameMat } from './auto-split'
import { applyPageSelection } from './selection'

/** 两个源文件（mi=0/1），mi=0 有整段与另名段，mi=1 有整段——覆盖跟随名/非跟随名/跨源三种段 */
function fixture(): DraftState {
  return {
    mats: [
      { partIndex: 0, n: '起诉状.pdf', k: 'pdf', pages: 3 },
      { partIndex: 1, n: '证据.pdf', k: 'pdf', pages: 2 },
    ],
    segs: [
      { id: 'seg-a', t: '起诉状', fn: '起诉状.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }], manual: false },
      { id: 'seg-b', t: '证据', fn: '起诉状-手动改名', refs: [{ mi: 0, p: 1 }], manual: true },
      { id: 'seg-c', t: '证据', fn: '证据.pdf', refs: [{ mi: 1, p: 1 }, { mi: 1, p: 2 }], manual: false },
    ],
    infos: [],
  }
}

describe('renameMat 源素材改名', () => {
  it('首次改名：写 customName，仍用源文件名的段同步跟随', () => {
    const d = renameMat(fixture(), 0, '新起诉状')
    expect(d.mats[0]!.customName).toBe('新起诉状')
    expect(d.segs[0]!.fn).toBe('新起诉状')
    // 手动改过名的段与别的源文件不受影响
    expect(d.segs[1]!.fn).toBe('起诉状-手动改名')
    expect(d.segs[2]!.fn).toBe('证据.pdf')
    expect(d.mats[1]!.customName).toBeUndefined()
  })

  it('二次改名：跟随段跟着第二次的名字走（不是只认源文件名）', () => {
    const once = renameMat(fixture(), 0, '第一次')
    const twice = renameMat(once, 0, '第二次')
    expect(twice.mats[0]!.customName).toBe('第二次')
    expect(twice.segs[0]!.fn).toBe('第二次')
  })

  it('改回源文件名：清除 customName，跟随段名一并还原', () => {
    const once = renameMat(fixture(), 0, '新起诉状')
    const reverted = renameMat(once, 0, '起诉状.pdf')
    expect(reverted.mats[0]!.customName).toBeUndefined()
    expect(reverted.segs[0]!.fn).toBe('起诉状.pdf')
    expect(reverted.segs[1]!.fn).toBe('起诉状-手动改名')
  })

  it('同名提交与空名：返回原引用，不触发草稿保存', () => {
    const d = fixture()
    expect(renameMat(d, 0, '')).toBe(d)
    expect(renameMat(d, 0, '  ')).toBe(d)
    expect(renameMat(d, 9, 'whatever')).toBe(d)
    const renamed = renameMat(d, 0, '新起诉状')
    expect(renameMat(renamed, 0, '新起诉状')).toBe(renamed)
  })
})

/** 建议构造捷径：start-end 页区间 */
function sug(start: number, end: number, over: Partial<PdfSplitSegmentSuggestion> = {}): PdfSplitSegmentSuggestion {
  return {
    page_start: start,
    page_end: end,
    segment_type: 'indictment',
    segment_label: '起诉状',
    filename: `part-${start}.pdf`,
    confidence: 0.9,
    review_flag: '',
    ...over,
  }
}

/** 单源场景：mi=0 共 3 页一整段（未被人工动过） */
function singleSourceFixture(): DraftState {
  return {
    mats: [{ partIndex: 0, n: '合并扫描.pdf', k: 'pdf', pages: 3 }],
    segs: [
      { id: 'seg-x', t: '', fn: '合并扫描.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }], manual: false },
    ],
    infos: [],
  }
}

/** 两源场景：mi=0（3 页）+ mi=1（2 页），各一整段，均未被人工动过 */
function twoSourceFixture(): DraftState {
  return {
    mats: [
      { partIndex: 0, n: '起诉状.pdf', k: 'pdf', pages: 3 },
      { partIndex: 1, n: '证据.pdf', k: 'pdf', pages: 2 },
    ],
    segs: [
      { id: 'seg-p', t: '', fn: '起诉状.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }], manual: false },
      { id: 'seg-q', t: '', fn: '证据.pdf', refs: [{ mi: 1, p: 1 }, { mi: 1, p: 2 }], manual: false },
    ],
    infos: [],
  }
}

describe('applyAutoSplit 云端拆分建议应用', () => {
  it('整覆盖建议替换原整段：类型/文件名/复核标记逐项落地，页引用展开连续', () => {
    const d = applyAutoSplit(singleSourceFixture(), 0, [
      sug(1, 1, { segment_type: 'unrecognized' }),
      sug(2, 3, { segment_label: '证据清单', filename: 'evidence.pdf', review_flag: 'low_conf', confidence: 0.4 }),
    ])
    expect(d.segs).toHaveLength(2)
    // unrecognized 段类型清空
    expect(d.segs[0]).toMatchObject({ t: '', fn: 'part-1', manual: false, reviewFlag: '', confidence: 0.9 })
    expect(d.segs[0]!.refs).toEqual([{ mi: 0, p: 1 }])
    // 正常段带 label、.pdf 后缀去掉、复核标记与置信度透传
    expect(d.segs[1]).toMatchObject({
      t: '证据清单',
      fn: 'evidence',
      reviewFlag: 'low_conf',
      confidence: 0.4,
      manual: false,
    })
    expect(d.segs[1]!.refs).toEqual([{ mi: 0, p: 2 }, { mi: 0, p: 3 }])
  })

  it('原有段有 manual 或跨源引用时不应用，返回原引用', () => {
    const d0 = fixture() // mi=0 上有 manual 段（起诉状-手动改名）
    expect(applyAutoSplit(d0, 0, [sug(1, 3)])).toBe(d0)
    const cross = {
      ...singleSourceFixture(),
      segs: [
        {
          id: 'seg-cross',
          t: '',
          fn: 'x.pdf',
          refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }, { mi: 1, p: 1 }],
          manual: false,
        },
      ],
      mats: [
        ...singleSourceFixture().mats,
        { partIndex: 1, n: '别的.pdf', k: 'pdf' as const, pages: 1 },
      ],
    }
    expect(applyAutoSplit(cross, 0, [sug(1, 3)])).toBe(cross)
  })

  it('建议未整覆盖全部页时不应用（有洞 / 全部建议非法）', () => {
    const d0 = singleSourceFixture()
    expect(applyAutoSplit(d0, 0, [sug(1, 2)])).toBe(d0) // 缺第 3 页
    expect(applyAutoSplit(d0, 0, [sug(2, 1)])).toBe(d0) // end < start，全被过滤后覆盖为空
    expect(applyAutoSplit(d0, 0, [sug(0, 3)])).toBe(d0) // 页码从 0 起，非法
  })

  it('非法建议被过滤后仍整覆盖时照常应用（区间过滤）', () => {
    const d = applyAutoSplit(singleSourceFixture(), 0, [sug(1, 3), sug(9, 12)])
    expect(d.segs).toHaveLength(1)
    expect(d.segs[0]!.refs).toHaveLength(3)
  })

  it('非 pdf 素材 / 不存在的素材 / 空建议：返回原引用', () => {
    const d0 = fixture()
    expect(applyAutoSplit(d0, 9, [sug(1, 1)])).toBe(d0)
    expect(applyAutoSplit(d0, 0, [])).toBe(d0)
  })

  it('多源草稿：替换只针对目标源，其他源的段保持并按源序重排', () => {
    const d = applyAutoSplit(twoSourceFixture(), 0, [
      sug(1, 1, { segment_label: '起诉状' }),
      sug(2, 3, { segment_label: '证据' }),
    ])
    // mi=0 换成两段建议，mi=1 的整段保留，顺序按「源序+页序」
    expect(d.segs.map((sg) => sg.fn)).toEqual(['part-1', 'part-2', '证据.pdf'])
    expect(d.segs.flatMap((sg) => sg.refs)).toHaveLength(5)
  })
})

describe('canAutoSplitMat', () => {
  it('未被人工动过的源可以自动拆分；有 manual 段的源不行', () => {
    const d = fixture() // mi=0 有 manual 段（起诉状-手动改名）
    expect(canAutoSplitMat(d, 0)).toBe(false)
    expect(canAutoSplitMat(d, 1)).toBe(true)
    expect(canAutoSplitMat(twoSourceFixture(), 0)).toBe(true)
  })

  it('切页产生的人工段同样阻断该源', () => {
    const d = applyPageSelection(twoSourceFixture(), [{ mi: 1, p: 2 }])
    expect(canAutoSplitMat(d, 1)).toBe(false)
    expect(canAutoSplitMat(d, 0)).toBe(true)
  })
})
