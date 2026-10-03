import { vi } from 'vitest'

import type { DraftState } from '../types'

// segments → resolve → ../api 的传递依赖在模块加载时读 localStorage（node 环境没有），打桩截断
vi.mock('../api', () => ({ fetchAttachmentBytes: vi.fn() }))

import {
  appendMatsToDraft,
  markAllSegsDone,
  mergeSegment,
  renameSegment,
  resetSegments,
  setPackAssign,
  setPackStatus,
  setSegmentType,
  splitSegment,
  toggleSegDone,
} from './segments'
import { ensureSegIds } from './seg-id'

function fixture(): DraftState {
  return {
    mats: [
      { partIndex: 0, n: '起诉状.pdf', k: 'pdf', pages: 3 },
      { partIndex: 1, n: '证据.pdf', k: 'pdf', pages: 2 },
    ],
    segs: [
      { id: 'seg-a', t: '起诉状', fn: '起诉状.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }], manual: false },
      { id: 'seg-b', t: '证据', fn: '证据.pdf', refs: [{ mi: 1, p: 1 }, { mi: 1, p: 2 }], manual: true },
    ],
    infos: [],
  }
}

describe('splitSegment', () => {
  it('在第 k 页缝切开：前段保留类型且标记人工，新段类型清空、名取来源名', () => {
    const d = splitSegment(fixture(), 0, 1)
    expect(d.segs).toHaveLength(3)
    expect(d.segs[0]).toMatchObject({ t: '起诉状', fn: '起诉状.pdf', manual: true })
    expect(d.segs[0]!.refs).toEqual([{ mi: 0, p: 1 }, { mi: 0, p: 2 }])
    expect(d.segs[1]).toMatchObject({ t: '', fn: '起诉状.pdf', manual: true })
    expect(d.segs[1]!.refs).toEqual([{ mi: 0, p: 3 }])
    // 后面的段原样保留
    expect(d.segs[2]).toMatchObject({ t: '证据' })
  })

  it('越界守卫：si / k 越界或单页段原样返回', () => {
    const d = fixture()
    expect(splitSegment(d, -1, 0)).toBe(d)
    expect(splitSegment(d, 9, 0)).toBe(d)
    expect(splitSegment(d, 0, -1)).toBe(d)
    expect(splitSegment(d, 0, 2)).toBe(d) // k 只能取 0..refs.length-2
    // 单页段（切完再切尾段）不可再切
    const once = splitSegment(d, 0, 1)
    expect(splitSegment(once, 1, 0)).toBe(once)
  })
})

describe('mergeSegment', () => {
  it('段并入前一段：refs 拼接、manual 取或；首段不可并入', () => {
    const d0 = fixture()
    const d = mergeSegment(d0, 1)
    expect(d.segs).toHaveLength(1)
    expect(d.segs[0]!.refs).toEqual([
      { mi: 0, p: 1 },
      { mi: 0, p: 2 },
      { mi: 0, p: 3 },
      { mi: 1, p: 1 },
      { mi: 1, p: 2 },
    ])
    // 前段 manual=false，后段 manual=true → 合并后人工
    expect(d.segs[0]!.manual).toBe(true)
    expect(mergeSegment(d0, 0)).toBe(d0) // si=0 不可并入
  })
})

describe('段 id 稳定性', () => {
  it('splitSegment：前半段沿用原段 id，新段拿到与全部既有段不重复的唯一 id', () => {
    const d0 = fixture()
    const d = splitSegment(d0, 0, 1)
    expect(d.segs[0]!.id).toBe(d0.segs[0]!.id)
    expect(d.segs[1]!.id).not.toBe(d0.segs[0]!.id)
    const ids = d.segs.map((sg) => sg.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('mergeSegment：合并结果保留前段 id；先切后并 id 仍全局唯一', () => {
    const d0 = fixture()
    const split = splitSegment(d0, 0, 1)
    const merged = mergeSegment(split, 1)
    expect(merged.segs[0]!.id).toBe(d0.segs[0]!.id)
    const ids = merged.segs.map((sg) => sg.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('resetSegments：重新生成的初始分段 id 唯一', () => {
    const d = resetSegments(fixture())
    const ids = d.segs.map((sg) => sg.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('ensureSegIds：存量无 id 草稿兜底补齐，已有 id 的原样保留', () => {
    const legacy = {
      ...fixture(),
      segs: fixture().segs.map(({ id: _id, ...sg }) => sg),
    } as unknown as DraftState
    const d = ensureSegIds(legacy)
    expect(d.segs.every((sg) => typeof sg.id === 'string' && sg.id)).toBe(true)
    const ids = d.segs.map((sg) => sg.id)
    expect(new Set(ids).size).toBe(ids.length)
    // 已有 id 的草稿返回原引用，不重复赋 id
    const d0 = fixture()
    expect(ensureSegIds(d0)).toBe(d0)
  })
})

describe('段属性操作', () => {
  it('setSegmentType 改类型；同值返回原引用', () => {
    const d0 = fixture()
    const d = setSegmentType(d0, 0, '答辩状')
    expect(d.segs[0]!.t).toBe('答辩状')
    expect(setSegmentType(d, 0, '答辩状')).toBe(d)
    expect(setSegmentType(d0, 9, 'x')).toBe(d0)
  })

  it('renameSegment 去首尾空白；空名/同名返回原引用', () => {
    const d0 = fixture()
    const d = renameSegment(d0, 0, '  新名字.pdf  ')
    expect(d.segs[0]!.fn).toBe('新名字.pdf')
    expect(renameSegment(d0, 0, '   ')).toBe(d0)
    expect(renameSegment(d0, 0, '起诉状.pdf')).toBe(d0)
    expect(renameSegment(d0, -1, 'x')).toBe(d0)
  })

  it('toggleSegDone 翻转；markAllSegsDone 全勾且已全勾返回原引用', () => {
    const d0 = fixture()
    const d = toggleSegDone(d0, 1)
    expect(d.segs[1]!.done).toBe(true)
    expect(toggleSegDone(d, 1).segs[1]!.done).toBe(false)
    const all = markAllSegsDone(d0)
    expect(all.segs.every((sg) => sg.done)).toBe(true)
    expect(markAllSegsDone(all)).toBe(all)
  })
})

describe('resetSegments', () => {
  it('恢复为每源一整段的初始分段', () => {
    const d = resetSegments(splitSegment(fixture(), 0, 0))
    expect(d.segs).toHaveLength(2)
    expect(d.segs[0]).toMatchObject({ t: '', fn: '起诉状.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }], manual: false })
    expect(d.segs[1]).toMatchObject({ t: '', fn: '证据.pdf' })
  })
})

describe('材料包状态与追加', () => {
  it('setPackStatus 换状态；同状态返回原引用', () => {
    const d0 = fixture()
    expect(setPackStatus(d0, 'done').status).toBe('done')
    const d1 = setPackStatus(d0, 'done')
    expect(setPackStatus(d1, 'done')).toBe(d1)
  })

  it('setPackAssign 写入归案信息并置 done', () => {
    const assign = { target: 'existing', caseId: 12, caseTitle: '合同纠纷' } as const
    const d = setPackAssign(fixture(), assign)
    expect(d.assign).toBe(assign)
    expect(d.status).toBe('done')
  })

  it('appendMatsToDraft 追加素材并生成覆盖全页的默认段', () => {
    const d0 = fixture()
    const added = [{ partIndex: 2, n: '补充.pdf', k: 'pdf' as const, pages: 2 }]
    const d = appendMatsToDraft(d0, added)
    expect(d.mats).toHaveLength(3)
    expect(d.segs).toHaveLength(3)
    expect(d.segs[2]).toMatchObject({ t: '', fn: '补充.pdf', manual: false })
    expect(d.segs[2]!.refs).toEqual([{ mi: 2, p: 1 }, { mi: 2, p: 2 }])
    expect(appendMatsToDraft(d0, [])).toBe(d0)
  })
})
