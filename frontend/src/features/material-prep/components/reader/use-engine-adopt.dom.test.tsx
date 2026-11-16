// @vitest-environment jsdom
/**
 * 「采用 → 进编辑态预填 → 保存后自动勾选已核对」的编排测试。
 *
 * 回归背景：两侧都可能错。实测同一处姓名被两个引擎读成三个不同结果，
 * 此时点任何一边的「采用」直接写入 = 把错的写进诉状引用。
 * 所以采用改成「拿该侧全文当起点进编辑态」。
 */
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { DraftState } from '../../types'
import { useEngineAdopt } from './use-engine-adopt'

function draft(blocks = [{ page: 3, text: '截止至2023年, 张甲某贷款余额1208元' }]): DraftState {
  return {
    mats: [{ partIndex: 0, n: 'x.pdf', k: 'pdf', pages: 5 }],
    segs: [
      {
        id: 's1',
        t: '',
        fn: 'x.pdf',
        refs: [{ mi: 0, p: 3 }],
        manual: false,
        blocks: blocks.map((b) => ({
          ...b,
          type: 'paragraph',
          rect: { x: 0, y: 0, w: 1, h: 0.1, approx: false, precision: 'exact' as const },
        })),
      },
    ],
    infos: [],
  }
}

function setup(d: DraftState = draft()) {
  const onToggleChecked = vi.fn()
  const onGotoPage = vi.fn()
  const onOpenMd = vi.fn()
  const { result } = renderHook(() =>
    useEngineAdopt({ draft: d, focusedSeg: 0, onToggleChecked, onGotoPage, onOpenMd }),
  )
  return { result, onToggleChecked, onGotoPage, onOpenMd }
}

describe('useEngineAdopt', () => {
  it('采用不直接写库，而是发出带种子文本的编辑请求', () => {
    const { result, onGotoPage, onOpenMd } = setup()
    act(() => {
      result.current.adopt(3, '截止至2023年, 张甲某贷款余额1208元', 'mineru', 'dk-1')
    })
    // 关键：没有直接改正文的调用（这里没有 editBlock），只有编辑请求
    expect(result.current.editRequest?.seed).toBe('截止至2023年, 张甲某贷款余额1208元')
    expect(result.current.editRequest?.key).toContain('s1:3')
    // 顺带跳到原页、展开右栏，让律师能对着原件改
    expect(onGotoPage).toHaveBeenCalledWith(0, 3)
    expect(onOpenMd).toHaveBeenCalled()
  })

  it('保存后自动勾选该条分歧「已核对」，且只勾一次', () => {
    const { result, onToggleChecked } = setup()
    act(() => {
      result.current.adopt(3, '截止至2023年, 张甲某贷款余额1208元', 'mineru', 'dk-1')
    })
    act(() => result.current.commit())
    expect(onToggleChecked).toHaveBeenCalledWith('dk-1', true)

    // 再调一次不重复勾（pendingCheckedKey 已清空）
    act(() => result.current.commit())
    expect(onToggleChecked).toHaveBeenCalledTimes(1)
  })

  it('不是分歧发起的编辑（requestEdit）不会误勾任何分歧', () => {
    const { result, onToggleChecked } = setup()
    act(() => result.current.requestEdit({ key: 's1:3:0' }))
    act(() => result.current.commit())
    expect(onToggleChecked).not.toHaveBeenCalled()
  })

  it('找不到能容纳该文本的块时什么都不做（宁可不改，也不写错块）', () => {
    const { result, onGotoPage } = setup()
    act(() => {
      result.current.adopt(3, '这段文字在块里根本不存在', 'mineru', 'dk-1')
    })
    expect(result.current.editRequest).toBeNull()
    expect(onGotoPage).not.toHaveBeenCalled()
  })

  it('页号对不上也不动（防止把别页的文字写进本页块）', () => {
    const { result } = setup()
    act(() => {
      result.current.adopt(99, '截止至2023年, 张甲某贷款余额1208元', 'mineru', 'dk-1')
    })
    expect(result.current.editRequest).toBeNull()
  })

  it('clearRequest 清空请求（供 onEditRequestHandled 调用）', () => {
    const { result } = setup()
    act(() => {
      result.current.adopt(3, '截止至2023年, 张甲某贷款余额1208元', 'mineru', 'dk-1')
    })
    expect(result.current.editRequest).not.toBeNull()
    act(() => result.current.clearRequest())
    expect(result.current.editRequest).toBeNull()
  })
})
