// @vitest-environment jsdom
/**
 * RerunConfirmDialog 测试（jsdom）。
 *
 * 它守的是「重跑前必须让律师看清后果」这条底线，所以断言集中在三件事：
 * 1. 哪几份材料、改过什么（正文 / 名字 / 类型）要逐个列出来，不能只报个总数；
 * 2. 两个选项各自的后果文案都在（「会被覆盖」vs「新正文不会进来」）；
 * 3. 取消 = 整次重跑不执行，三个回调互不串线。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RerunConfirmDialog } from './RerunConfirmDialog'
import type { AutoSplitConflict } from '../../draft'
import type { DraftState } from '../../types'

const draft = {
  mats: [
    { partIndex: 0, n: '借款合同.pdf', k: 'pdf', pages: 3 },
    { partIndex: 1, n: '流水.pdf', k: 'pdf', pages: 10, customName: '银行流水' },
  ],
  segs: [],
  infos: [],
} as unknown as DraftState

const conflicts: AutoSplitConflict[] = [
  {
    mi: 0,
    edited: [
      { si: 0, name: '借款合同', what: ['md'] },
      { si: 1, name: '借条', what: ['name', 'type'] },
    ],
  },
]

function props(over: Record<string, unknown> = {}) {
  return {
    conflicts,
    draft,
    onCancel: vi.fn(),
    onKeepEdits: vi.fn(),
    onOverwrite: vi.fn(),
    ...over,
  }
}

describe('RerunConfirmDialog', () => {
  it('没有冲突时整块不渲染', () => {
    const { container } = render(<RerunConfirmDialog {...props({ conflicts: [] })} />)
    expect(container.textContent).toBe('')
  })

  it('列出材料名与逐条的改动类型（正文 / 名字 / 类型）', () => {
    render(<RerunConfirmDialog {...props()} />)

    expect(screen.getByText('借款合同.pdf')).toBeTruthy()
    expect(screen.getByText(/「借款合同」改过 正文/)).toBeTruthy()
    expect(screen.getByText(/「借条」改过 名字 \/ 类型/)).toBeTruthy()
  })

  it('自定义名优先于原文件名（律师认的是自己起的名字）', () => {
    render(
      <RerunConfirmDialog
        {...props({ conflicts: [{ mi: 1, edited: [{ si: 0, name: '流水', what: ['md'] }] }] })}
      />,
    )
    expect(screen.getByText('银行流水')).toBeTruthy()
    expect(screen.queryByText('流水.pdf')).toBeNull()
  })

  it('两个选项的后果都写清楚：覆盖不可撤销 / 新正文不会进来', () => {
    render(<RerunConfirmDialog {...props()} />)

    expect(screen.getByText(/这些改动会被覆盖，且不可撤销/)).toBeTruthy()
    expect(screen.getByText(/这些段对应的正文不会进来/)).toBeTruthy()
  })

  it('三个按钮各自回调，互不串线', () => {
    const onCancel = vi.fn()
    const onKeepEdits = vi.fn()
    const onOverwrite = vi.fn()
    render(<RerunConfirmDialog {...props({ onCancel, onKeepEdits, onOverwrite })} />)

    fireEvent.click(screen.getByRole('button', { name: '保留我的修改' }))
    expect(onKeepEdits).toHaveBeenCalledTimes(1)
    expect(onOverwrite).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '用识别结果覆盖' }))
    expect(onOverwrite).toHaveBeenCalledTimes(1)
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('取消 = 整次重跑不执行（只走 onCancel）', () => {
    const onCancel = vi.fn()
    const onKeepEdits = vi.fn()
    const onOverwrite = vi.fn()
    render(<RerunConfirmDialog {...props({ onCancel, onKeepEdits, onOverwrite })} />)

    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onKeepEdits).not.toHaveBeenCalled()
    expect(onOverwrite).not.toHaveBeenCalled()
  })

  it('多份材料各有冲突时每份都列出来', () => {
    render(
      <RerunConfirmDialog
        {...props({
          conflicts: [
            { mi: 0, edited: [{ si: 0, name: '甲', what: ['md'] }] },
            { mi: 1, edited: [{ si: 2, name: '乙', what: ['name'] }] },
          ],
        })}
      />,
    )
    expect(screen.getByText('借款合同.pdf')).toBeTruthy()
    expect(screen.getByText('银行流水')).toBeTruthy()
  })
})
