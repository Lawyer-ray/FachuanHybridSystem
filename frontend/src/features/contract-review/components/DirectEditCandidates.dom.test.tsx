// @vitest-environment jsdom
/**
 * DirectEditCandidates 展示契约（jsdom）。
 *
 * 这组卡片与 RevisionList 不同：没有驳回、没有等级，只有「挑一条」。
 * 要钉住的两条：长改写默认折叠可展开；落盘中全组禁用防重复提交。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DirectEditCandidates } from './DirectEditCandidates'
import type { DirectEditCandidate } from '../types'

function candidate(over: Partial<DirectEditCandidate> = {}): DirectEditCandidate {
  return { suggested: '甲方应于收到发票后三十日内支付。', reason: '', ...over }
}

describe('DirectEditCandidates', () => {
  it('空候选不渲染任何内容', () => {
    const { container } = render(
      <DirectEditCandidates selection="原文" candidates={[]} onAccept={vi.fn()} busyIndex={null} />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('展示选区摘要与候选数量，短选区不截断', () => {
    render(
      <DirectEditCandidates selection="甲方付款" candidates={[candidate(), candidate({ suggested: '乙' })]} onAccept={vi.fn()} busyIndex={null} />,
    )
    expect(screen.getByText(/为「甲方付款」生成 2 个改法/)).toBeTruthy()
  })

  it('长选区截断到 24 字并加省略号', () => {
    const long = '甲'.repeat(30)
    render(<DirectEditCandidates selection={long} candidates={[candidate()]} onAccept={vi.fn()} busyIndex={null} />)
    expect(screen.getByText(new RegExp(`为「${'甲'.repeat(24)}…」生成 1 个改法`))).toBeTruthy()
  })

  it('超过 180 字的改写默认折叠，点「展开全文」后可「收起」', () => {
    const long = '改'.repeat(200)
    render(<DirectEditCandidates selection="原文" candidates={[candidate({ suggested: long })]} onAccept={vi.fn()} busyIndex={null} />)

    fireEvent.click(screen.getByRole('button', { name: '展开全文' }))
    expect(screen.getByRole('button', { name: '收起' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '收起' }))
    expect(screen.getByRole('button', { name: '展开全文' })).toBeTruthy()
  })

  it('短改写不出现折叠入口', () => {
    render(<DirectEditCandidates selection="原文" candidates={[candidate()]} onAccept={vi.fn()} busyIndex={null} />)
    expect(screen.queryByRole('button', { name: '展开全文' })).toBeNull()
  })

  it('有 reason 时在标题行展示依据', () => {
    render(
      <DirectEditCandidates
        selection="原文"
        candidates={[candidate({ reason: '依据：《民法典》第509条' })]}
        onAccept={vi.fn()}
        busyIndex={null}
      />,
    )
    expect(screen.getByText('依据：《民法典》第509条')).toBeTruthy()
  })

  it('采纳回传下标与原候选对象', () => {
    const onAccept = vi.fn()
    const items = [candidate({ suggested: 'A' }), candidate({ suggested: 'B' })]
    render(<DirectEditCandidates selection="原文" candidates={items} onAccept={onAccept} busyIndex={null} />)

    const acceptButtons = screen.getAllByRole('button', { name: /采纳这条/ })
    fireEvent.click(acceptButtons[1] as HTMLElement)
    expect(onAccept).toHaveBeenCalledWith(1, items[1])
  })

  it('落盘中：该条显示「写入中…」，其余按钮全部禁用（防重复提交）', () => {
    const onAccept = vi.fn()
    render(
      <DirectEditCandidates selection="原文" candidates={[candidate(), candidate({ suggested: 'B' })]} onAccept={onAccept} busyIndex={0} />,
    )

    expect(screen.getByText('写入中…')).toBeTruthy()
    const buttons = screen.getAllByRole('button')
    for (const b of buttons) expect((b as HTMLButtonElement).disabled).toBe(true)

    fireEvent.click(buttons[1] as HTMLElement)
    expect(onAccept).not.toHaveBeenCalled()
  })
})
