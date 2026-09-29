import type { DraftState } from '../types'
import { renameMat } from './auto-split'

/** 两个源文件（mi=0/1），mi=0 有整段与另名段，mi=1 有整段——覆盖跟随名/非跟随名/跨源三种段 */
function fixture(): DraftState {
  return {
    mats: [
      { partIndex: 0, n: '起诉状.pdf', k: 'pdf', pages: 3 },
      { partIndex: 1, n: '证据.pdf', k: 'pdf', pages: 2 },
    ],
    segs: [
      { t: '起诉状', fn: '起诉状.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }], manual: false },
      { t: '证据', fn: '起诉状-手动改名', refs: [{ mi: 0, p: 1 }], manual: true },
      { t: '证据', fn: '证据.pdf', refs: [{ mi: 1, p: 1 }, { mi: 1, p: 2 }], manual: false },
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
