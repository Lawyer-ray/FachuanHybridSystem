// @vitest-environment jsdom
/**
 * 「采用 / 修改」两条路径的编排测试。
 *
 * 分工（用户明确要求的语义）：
 * - **采用** = 确认这一侧对 → **直接写入正文** + 标已核对，不进编辑态
 *   （采用的是明确表态，再要一次确认是绕）
 * - **修改** = 两侧都不对 → 进编辑态，预填主引擎文本作起点，保存后标已核对
 */
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { DraftState } from '../../types'
import { useEngineAdopt } from './use-engine-adopt'

const GOOD = '截止至2023年, 张甲某贷款余额1208元'

function draft(): DraftState {
  return {
    mats: [{ partIndex: 0, n: 'x.pdf', k: 'pdf', pages: 5 }],
    segs: [
      {
        id: 's1',
        t: '',
        fn: 'x.pdf',
        refs: [{ mi: 0, p: 3 }],
        manual: false,
        blocks: [
          {
            page: 3,
            type: 'paragraph',
            text: GOOD,
            rect: { x: 0, y: 0, w: 1, h: 0.1, approx: false, precision: 'exact' as const },
          },
        ],
      },
    ],
    infos: [],
  }
}

function setup() {
  const editBlock = vi.fn()
  const onToggleChecked = vi.fn()
  const onGotoPage = vi.fn()
  const onOpenMd = vi.fn()
  const { result } = renderHook(() =>
    useEngineAdopt({
      draft: draft(),
      focusedSeg: 0,
      editBlock,
      onToggleChecked,
      onGotoPage,
      onOpenMd,
    }),
  )
  return { result, editBlock, onToggleChecked, onGotoPage, onOpenMd }
}

describe('采用：确认这一侧对，直接写入', () => {
  it('直接写库，不进编辑态', () => {
    const { result, editBlock, onGotoPage } = setup()
    act(() => {
      result.current.adopt(3, GOOD, 'mineru', 'dk-1')
    })
    expect(editBlock).toHaveBeenCalledWith(0, expect.stringContaining('s1:3'), GOOD)
    // 关键：没有发出编辑请求（采用不该再要一次确认）
    expect(result.current.editRequest).toBeNull()
    expect(onGotoPage).toHaveBeenCalledWith(0, 3)
  })

  it('写入后立刻标为已核对（律师已明确表态）', () => {
    const { result, onToggleChecked } = setup()
    act(() => {
      result.current.adopt(3, GOOD, 'mineru', 'dk-1')
    })
    expect(onToggleChecked).toHaveBeenCalledWith('dk-1', true)
  })

  it('找不到能容纳该文本的块时什么都不做（宁可不改，也不写错块）', () => {
    const { result, editBlock } = setup()
    act(() => {
      result.current.adopt(3, '这段文字在块里不存在', 'mineru', 'dk-1')
    })
    expect(editBlock).not.toHaveBeenCalled()
  })

  it('页号对不上也不动（防止把别页文字写进本页块）', () => {
    const { result, editBlock } = setup()
    act(() => {
      result.current.adopt(99, GOOD, 'mineru', 'dk-1')
    })
    expect(editBlock).not.toHaveBeenCalled()
  })
})

describe('修改：两侧都不对，进编辑态', () => {
  it('发出带种子文本的编辑请求，且不直接写库', () => {
    const { result, editBlock, onGotoPage, onOpenMd } = setup()
    act(() => {
      result.current.edit(3, GOOD, 'dk-1')
    })
    expect(result.current.editRequest?.seed).toBe(GOOD)
    expect(result.current.editRequest?.key).toContain('s1:3')
    expect(editBlock).not.toHaveBeenCalled() // 还没写，等律师保存
    expect(onGotoPage).toHaveBeenCalledWith(0, 3)
    expect(onOpenMd).toHaveBeenCalled()
  })

  it('保存后自动勾选该条分歧「已核对」，且只勾一次', () => {
    const { result, onToggleChecked } = setup()
    act(() => {
      result.current.edit(3, GOOD, 'dk-1')
    })
    act(() => result.current.commit())
    expect(onToggleChecked).toHaveBeenCalledWith('dk-1', true)

    act(() => result.current.commit())
    expect(onToggleChecked).toHaveBeenCalledTimes(1)
  })

  it('clearRequest 清空请求（供 onEditRequestHandled 调用）', () => {
    const { result } = setup()
    act(() => {
      result.current.edit(3, GOOD, 'dk-1')
    })
    expect(result.current.editRequest).not.toBeNull()
    act(() => result.current.clearRequest())
    expect(result.current.editRequest).toBeNull()
  })
})

describe('页面框双击进来的 requestEdit', () => {
  it('不会误勾任何分歧（它不是分歧发起的）', () => {
    const { result, onToggleChecked } = setup()
    act(() => result.current.requestEdit({ key: 's1:3:0' }))
    act(() => result.current.commit())
    expect(onToggleChecked).not.toHaveBeenCalled()
  })
})
