// @vitest-environment jsdom
/**
 * PartyPicker 测试（jsdom）。
 *
 * 这是标签式检索填报组件，核心不变量：
 * - 顿号分隔的字符串 ↔ 标签数组的互转（含去空白、去空项）
 * - 重复标签不重复添加
 * - Enter 把自由文本加为标签、空输入不加
 * - Backspace 在输入为空时删最后一个标签
 * - aria-expanded 与下拉渲染条件同源（读屏器不报错状态）
 * - 点击外部关闭下拉
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const searchMock = vi.hoisted(() => vi.fn())
vi.mock('../../api', () => ({ searchClients: (...a: unknown[]) => searchMock(...a) }))

import { PartyPicker } from './PartyPicker'

function renderPicker(value = '', onChange = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  const utils = render(
    <PartyPicker value={value} onChange={onChange} placeholder="委托人" isOurClient />,
    { wrapper: wrap },
  )
  const input = utils.container.querySelector('[role="combobox"]') as HTMLInputElement
  return { ...utils, input, onChange }
}

beforeEach(() => {
  vi.clearAllMocks()
  searchMock.mockResolvedValue([])
})

describe('PartyPicker：标签渲染', () => {
  it('顿号分隔的 value 渲染成多个标签', () => {
    const { container, unmount } = renderPicker('张三、李四、王五')
    for (const n of ['张三', '李四', '王五']) {
      expect(within(container).getByText(n)).toBeTruthy()
    }
    unmount()
  })

  it('含空白项时被过滤（不会渲染空标签）', () => {
    const { container, unmount } = renderPicker('张三、 、李四')
    expect(within(container).getByText('张三')).toBeTruthy()
    expect(within(container).getByText('李四')).toBeTruthy()
    // 只应有两个删除按钮
    expect(container.querySelectorAll('[aria-label^="删除 "]')).toHaveLength(2)
    unmount()
  })

  it('空 value 不渲染任何标签', () => {
    const { container, unmount } = renderPicker('')
    expect(container.querySelectorAll('[aria-label^="删除 "]')).toHaveLength(0)
    unmount()
  })

  it('有标签时 placeholder 让位（避免与标签挤在一起）', () => {
    const { input, unmount } = renderPicker('张三')
    expect(input.placeholder).toBe('')
    unmount()
  })
})

describe('PartyPicker：删标签', () => {
  it('点删除按钮移除对应标签并回传剩余项', () => {
    const onChange = vi.fn()
    const { container, unmount } = renderPicker('张三、李四', onChange)

    fireEvent.click(within(container).getByRole('button', { name: '删除 张三' }))
    expect(onChange).toHaveBeenCalledWith('李四')
    unmount()
  })

  it('删到空时回传空串', () => {
    const onChange = vi.fn()
    const { container, unmount } = renderPicker('张三', onChange)

    fireEvent.click(within(container).getByRole('button', { name: '删除 张三' }))
    expect(onChange).toHaveBeenCalledWith('')
    unmount()
  })
})

describe('PartyPicker：添加标签', () => {
  it('Enter 把输入内容加为新标签', () => {
    const onChange = vi.fn()
    const { input, unmount } = renderPicker('', onChange)

    fireEvent.change(input, { target: { value: '王五' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith('王五')
    unmount()
  })

  it('已有标签时新标签以顿号追加', () => {
    const onChange = vi.fn()
    const { input, unmount } = renderPicker('张三', onChange)

    fireEvent.change(input, { target: { value: '李四' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith('张三、李四')
    unmount()
  })

  it('重复标签不重复添加', () => {
    const onChange = vi.fn()
    const { input, unmount } = renderPicker('张三', onChange)

    fireEvent.change(input, { target: { value: '张三' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onChange).not.toHaveBeenCalled()
    unmount()
  })

  it('空白输入不添加', () => {
    const onChange = vi.fn()
    const { input, unmount } = renderPicker('', onChange)

    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onChange).not.toHaveBeenCalled()
    unmount()
  })

  it('输入前后空白被 trim 后加入', () => {
    const onChange = vi.fn()
    const { input, unmount } = renderPicker('', onChange)

    fireEvent.change(input, { target: { value: '  王五  ' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith('王五')
    unmount()
  })
})

describe('PartyPicker：Backspace 删末项', () => {
  it('输入为空时 Backspace 删除最后一个标签', () => {
    const onChange = vi.fn()
    const { input, unmount } = renderPicker('张三、李四', onChange)

    fireEvent.keyDown(input, { key: 'Backspace' })
    expect(onChange).toHaveBeenCalledWith('张三')
    unmount()
  })

  it('输入非空时 Backspace 不删标签（正常编辑文本）', () => {
    const onChange = vi.fn()
    const { input, unmount } = renderPicker('张三', onChange)

    fireEvent.change(input, { target: { value: '李' } })
    fireEvent.keyDown(input, { key: 'Backspace' })
    expect(onChange).not.toHaveBeenCalled()
    unmount()
  })

  it('无标签时 Backspace 不做事', () => {
    const onChange = vi.fn()
    const { input, unmount } = renderPicker('', onChange)

    fireEvent.keyDown(input, { key: 'Backspace' })
    expect(onChange).not.toHaveBeenCalled()
    unmount()
  })
})

describe('PartyPicker：下拉与 ARIA', () => {
  it('aria-expanded 与是否有输入同源', () => {
    const { input, unmount } = renderPicker('')
    expect(input.getAttribute('aria-expanded')).toBe('false')

    fireEvent.change(input, { target: { value: '张' } })
    expect(input.getAttribute('aria-expanded')).toBe('true')

    // 清空输入后收起
    fireEvent.change(input, { target: { value: '' } })
    expect(input.getAttribute('aria-expanded')).toBe('false')
    unmount()
  })

  it('Esc 收起下拉', () => {
    const { input, unmount } = renderPicker('')
    fireEvent.change(input, { target: { value: '张' } })
    expect(input.getAttribute('aria-expanded')).toBe('true')

    fireEvent.keyDown(input, { key: 'Escape' })
    expect(input.getAttribute('aria-expanded')).toBe('false')
    unmount()
  })

  it('输入后展示检索候选', async () => {
    searchMock.mockResolvedValue([{ id: 1, name: '张三', kind: 'person' }])
    const { container, input, unmount } = renderPicker('')

    fireEvent.change(input, { target: { value: '张' } })
    await waitFor(() => expect(within(container).getByText('张三')).toBeTruthy())
    unmount()
  })

  it('点击外部关闭下拉', async () => {
    const { input, unmount } = renderPicker('')
    fireEvent.change(input, { target: { value: '张' } })
    expect(input.getAttribute('aria-expanded')).toBe('true')

    fireEvent.mouseDown(document.body)
    await waitFor(() => expect(input.getAttribute('aria-expanded')).toBe('false'))
    unmount()
  })
})
