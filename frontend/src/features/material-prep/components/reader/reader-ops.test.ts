/**
 * material-prep reader/reader-ops 单测（node 环境）。
 *
 * reader-ops 是「draft 不可变操作 → store.update」的接线工厂，draft 域逻辑
 * 保持真实：断言每个 op 都把对应纯函数下推给 update、pickPage/removeInfo
 * 走直通回调，selDetailOf 的跨段判定与越界页过滤。
 */
import { describe, expect, it, vi } from 'vitest'

import {
  addInfoField as infoAdd,
  setInfoValue as infoSetValue,
  setSegmentType as segSetType,
  renameSegment as segRename,
  mergeSegment as segMerge,
  splitSegment as segSplit,
  toggleSegDone as segToggleDone,
} from '../../draft'
import type { DraftState, InfoField } from '../../types'

import { buildFlowOps, buildMetaOps, selDetailOf } from './reader-ops'

function draftFixture(): DraftState {
  return {
    mats: [
      { partIndex: 0, n: 'a.pdf', k: 'pdf', pages: 4 },
      { partIndex: 1, n: 'b.jpg', k: 'photo', pages: 2 },
    ],
    segs: [
      { id: 's1', t: '起诉状', fn: '起诉状.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }], manual: false },
      { id: 's2', t: '证据材料', fn: '证据.pdf', refs: [{ mi: 0, p: 3 }, { mi: 0, p: 4 }, { mi: 1, p: 1 }], manual: true },
    ],
    infos: [],
  }
}

const field: InfoField = { k: '委托人', v: '', src: '', srcRef: null }

describe('buildFlowOps（draft 操作接线）', () => {
  it('五个段操作各自下推对应纯函数给 update，pickPage 直通调用方实现', () => {
    const update = vi.fn()
    const pickPage = vi.fn()
    const ops = buildFlowOps(update, pickPage)

    ops.setSegType(0, '借条')
    ops.renameSeg(0, '民事起诉状')
    ops.mergeSeg(0)
    ops.toggleDone(1)
    ops.splitSeg(0, 1)
    expect(update).toHaveBeenCalledTimes(5)

    const d = draftFixture()
    const fns = update.mock.calls.map(([fn]) => (fn as (x: DraftState) => DraftState)(d))
    expect(fns[0]).toEqual(segSetType(d, 0, '借条'))
    expect(fns[1]).toEqual(segRename(d, 0, '民事起诉状'))
    expect(fns[2]).toEqual(segMerge(d, 0))
    expect(fns[3]).toEqual(segToggleDone(d, 1))
    expect(fns[4]).toEqual(segSplit(d, 0, 1))

    ops.pickPage(2, 3)
    expect(pickPage).toHaveBeenCalledWith(2, 3)
    expect(update).toHaveBeenCalledTimes(5)
  })

  it('操作是不可变的：fixture 不被就地改写', () => {
    const update = vi.fn()
    const ops = buildFlowOps(update, vi.fn())
    const d = draftFixture()
    ops.setSegType(0, '借条')
    const [fn] = update.mock.calls[0] as [(x: DraftState) => DraftState]
    fn(d)
    expect(d.segs[0]!.t).toBe('起诉状')
  })
})

describe('buildMetaOps（右栏信息便签接线）', () => {
  it('addInfo / setValue 走 update 纯函数，removeInfo 走 store 同名 action（含下标校正）', () => {
    const update = vi.fn()
    const removeInfo = vi.fn()
    const ops = buildMetaOps(update, removeInfo)

    ops.addInfo(field)
    ops.setValue(0, '张三')
    const d = draftFixture()
    const fns = update.mock.calls.map(([fn]) => (fn as (x: DraftState) => DraftState)(d))
    expect(fns[0]).toEqual(infoAdd(d, field))
    expect(fns[1]).toEqual(infoSetValue(d, 0, '张三'))

    ops.removeInfo(0)
    expect(removeInfo).toHaveBeenCalledWith(0)
    expect(update).toHaveBeenCalledTimes(2)
  })
})

describe('selDetailOf（选中页汇总）', () => {
  it('同段两页：count=2、cross=false', () => {
    const d = draftFixture()
    expect(selDetailOf(d, [{ mi: 0, p: 1 }, { mi: 0, p: 2 }])).toEqual({ count: 2, cross: false })
  })

  it('跨段页（pdf + photo）：cross=true', () => {
    const d = draftFixture()
    expect(selDetailOf(d, [{ mi: 0, p: 1 }, { mi: 1, p: 1 }])).toEqual({ count: 2, cross: true })
  })

  it('越界页被过滤出跨段判定，但仍计入 count；空选 count=0', () => {
    const d = draftFixture()
    // mi 9 不存在 → 不参与 involved；mi 0 p 1 属段 0
    expect(selDetailOf(d, [{ mi: 0, p: 1 }, { mi: 9, p: 9 }])).toEqual({ count: 2, cross: false })
    expect(selDetailOf(d, [])).toEqual({ count: 0, cross: false })
  })
})
