// @vitest-environment jsdom
/**
 * RevisionList 交互测试（jsdom）。
 *
 * 左栏是律师的主战场，契约必须钉死：
 * - 待决策按「严重度→原顺序」，高危在前；已处理沉底且保留原顺序（工作轨迹）；
 * - 采纳后条目沉底、顶部计数减少；
 * - 驳回先展开理由框，确定才提交，取消不提交；
 * - 全部处理完给收尾提示。
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RevisionList } from './RevisionList'
import type { ReviewRevision } from '../types'

function rev(over: Partial<ReviewRevision> = {}): ReviewRevision {
  return {
    id: 'r1',
    ordinal: 0,
    kind: 'risk',
    severity: 'high',
    title: '付款节点过于提前',
    original: '甲方于每季度首月十日内支付。',
    suggested: '甲方于收到合规发票后三十日内支付。',
    reason: '依据：《民法典》第509条。',
    paragraph_index: 2,
    status: 'pending',
    reject_reason: '',
    ...over,
  }
}

const noop = () => {}

describe('RevisionList', () => {
  it('待决策按严重度排序：高 → 中 → 低', () => {
    render(
      <RevisionList
        items={[
          rev({ id: 'a', ordinal: 0, severity: 'low', title: '低风险项' }),
          rev({ id: 'b', ordinal: 1, severity: 'high', title: '高风险项' }),
          rev({ id: 'c', ordinal: 2, severity: 'medium', title: '中风险项' }),
        ]}
        busyId={null}
        onDecide={noop}
        onLocate={noop}
      />,
    )
    const titles = screen.getAllByText(/风险项$/).map((el) => el.textContent)
    expect(titles).toEqual(['高风险项', '中风险项', '低风险项'])
  })

  it('已处理的条目沉底并显示决策结果', () => {
    render(
      <RevisionList
        items={[
          rev({ id: 'a', ordinal: 0, title: '待办项' }),
          rev({ id: 'b', ordinal: 1, title: '已采纳项', status: 'accepted' }),
          rev({ id: 'c', ordinal: 2, title: '已驳回项', status: 'rejected', reject_reason: '客户坚持' }),
        ]}
        busyId={null}
        onDecide={noop}
        onLocate={noop}
      />,
    )
    expect(screen.getByText('待决策 · 1')).toBeTruthy()
    expect(screen.getByText('已处理 · 2')).toBeTruthy()
    expect(screen.getByText('已采纳 · 文档中已留痕')).toBeTruthy()
    expect(screen.getByText('已驳回 · 未改动（客户坚持）')).toBeTruthy()
  })

  it('点采纳 → 回调带正确的修订与动作', () => {
    const onDecide = vi.fn()
    render(
      <RevisionList items={[rev({ id: 'x1' })]} busyId={null} onDecide={onDecide} onLocate={noop} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /采纳/ }))
    expect(onDecide).toHaveBeenCalledWith(expect.objectContaining({ id: 'x1' }), 'accept')
  })

  it('点定位 → 触发 onLocate', () => {
    const onLocate = vi.fn()
    render(<RevisionList items={[rev({ id: 'x1' })]} busyId={null} onDecide={noop} onLocate={onLocate} />)
    fireEvent.click(screen.getByRole('button', { name: /定位/ }))
    expect(onLocate).toHaveBeenCalledWith(expect.objectContaining({ id: 'x1' }))
  })

  it('驳回先展开理由框，确定才提交（可留空）', () => {
    const onDecide = vi.fn()
    render(<RevisionList items={[rev()]} busyId={null} onDecide={onDecide} onLocate={noop} />)

    fireEvent.click(screen.getByRole('button', { name: /驳回/ }))
    // 此时还没提交
    expect(onDecide).not.toHaveBeenCalled()

    const box = screen.getByPlaceholderText(/驳回理由/)
    fireEvent.change(box, { target: { value: '客户坚持原条款' } })
    fireEvent.click(screen.getByRole('button', { name: '确定' }))

    expect(onDecide).toHaveBeenCalledWith(expect.anything(), 'reject', '客户坚持原条款')
  })

  it('驳回框取消不提交', () => {
    const onDecide = vi.fn()
    render(<RevisionList items={[rev()]} busyId={null} onDecide={onDecide} onLocate={noop} />)

    fireEvent.click(screen.getByRole('button', { name: /驳回/ }))
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onDecide).not.toHaveBeenCalled()
    // 回到操作按钮态
    expect(screen.getByRole('button', { name: /采纳/ })).toBeTruthy()
  })

  it('全部处理完给收尾提示', () => {
    render(
      <RevisionList
        items={[rev({ status: 'accepted' })]}
        busyId={null}
        onDecide={noop}
        onLocate={noop}
      />,
    )
    expect(screen.getByText(/全部建议已处理完/)).toBeTruthy()
    expect(screen.getByText('待决策 · 0')).toBeTruthy()
  })

  it('提交中禁用按钮（防连点）', () => {
    render(<RevisionList items={[rev({ id: 'busy1' })]} busyId="busy1" onDecide={noop} onLocate={noop} />)
    const accept = screen.getByRole('button', { name: /采纳/ })
    expect((accept as HTMLButtonElement).disabled).toBe(true)
  })

  it('风险计数只数待决策的', () => {
    render(
      <RevisionList
        items={[
          rev({ id: 'a', severity: 'high' }),
          rev({ id: 'b', ordinal: 1, severity: 'high', status: 'accepted' }),
        ]}
        busyId={null}
        onDecide={noop}
        onLocate={noop}
      />,
    )
    const header = screen.getByText('AI 建议修改').parentElement as HTMLElement
    expect(within(header).getByText('1 高')).toBeTruthy()
  })
})
