// @vitest-environment jsdom
/**
 * ReaderTopBar 测试（jsdom）。
 *
 * 顶栏只留两个真决策（不接 / 归案）与工具组，「关闭」与返回合并成同一动作，
 * 所以这里钉住：
 * - 未归类数只有 >0 才出现琥珀标（归完类顶栏回归安静）；
 * - 归案按钮恒可点（引导在 Reader 里做，不靠禁用按钮让人猜原因）；
 * - 每个入口都接线到对应回调。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ReaderTopBar } from './ReaderTopBar'

function props(over: Partial<Parameters<typeof ReaderTopBar>[0]> = {}) {
  return {
    title: '材料包 A',
    subtitle: '3 份材料 · 12 页',
    unclassified: 0,
    onBack: vi.fn(),
    onReject: vi.fn(),
    onAssign: vi.fn(),
    onRename: vi.fn(),
    ...over,
  }
}

describe('ReaderTopBar', () => {
  it('展示标题与副标题', () => {
    render(<ReaderTopBar {...props()} />)
    expect(screen.getByText('材料包 A')).toBeTruthy()
    expect(screen.getByText('3 份材料 · 12 页')).toBeTruthy()
  })

  it('未归类数为 0 时不出现琥珀标', () => {
    render(<ReaderTopBar {...props()} />)
    expect(screen.queryByText(/段未归类/)).toBeNull()
  })

  it('有未归类段时给出琥珀标与数量', () => {
    render(<ReaderTopBar {...props({ unclassified: 4 })} />)
    expect(screen.getByText('4 段未归类')).toBeTruthy()
  })

  it('工具组插槽原样渲染', () => {
    render(<ReaderTopBar {...props({ tools: <span>缩略图</span> })} />)
    expect(screen.getByText('缩略图')).toBeTruthy()
  })

  it('返回 / 重命名 / 不接 / 归案四个入口各自接线', () => {
    const p = props()
    render(<ReaderTopBar {...p} />)

    fireEvent.click(screen.getByLabelText('返回材料预处理列表'))
    fireEvent.click(screen.getByLabelText('重命名材料包'))
    fireEvent.click(screen.getByRole('button', { name: '不接' }))
    fireEvent.click(screen.getByRole('button', { name: '归案' }))

    expect(p.onBack).toHaveBeenCalledTimes(1)
    expect(p.onRename).toHaveBeenCalledTimes(1)
    expect(p.onReject).toHaveBeenCalledTimes(1)
    expect(p.onAssign).toHaveBeenCalledTimes(1)
  })

  it('归案按钮恒可点（未归类时由 Reader 跳转并提示，而不是禁用）', () => {
    render(<ReaderTopBar {...props({ unclassified: 9 })} />)
    expect((screen.getByRole('button', { name: '归案' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('两个决策按钮带 title 说明后果（不接=归档留痕不建案）', () => {
    render(<ReaderTopBar {...props()} />)
    expect(screen.getByRole('button', { name: '不接' }).title).toContain('已归档留痕')
    expect(screen.getByRole('button', { name: '归案' }).title).toContain('绑定案件')
  })
})
