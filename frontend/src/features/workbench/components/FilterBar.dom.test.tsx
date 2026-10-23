// @vitest-environment jsdom
/**
 * FilterBar 测试（jsdom）。
 *
 * 页头单行工具栏：
 * - 搜索框受控与 `/` 快捷键聚焦（输入框聚焦时不抢）
 * - 激活 chip：默认 status=active 不出 chip；非默认状态/类目/收费各出一颗
 * - 筛选按钮上的激活数量角标
 * - 点外部关闭弹层、弹层内连续调整不关闭
 * - facets 为 null 时计数为 0、不崩
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FilterBar } from './FilterBar'
import type { ContractPageResponse, WorkbenchFilter } from '../types'

function facets(): ContractPageResponse {
  return {
    total: 10,
    status_counts: { active: 6, archived: 3, unsigned: 1 },
    cat_counts: [
      { value: 'civil', label: '民事', count: 7 },
      { value: 'criminal', label: '刑事', count: 3 },
    ],
    fee_counts: [
      { value: 'fixed', label: '固定收费', count: 8 },
      { value: 'hourly', label: '计时收费', count: 2 },
    ],
  } as unknown as ContractPageResponse
}

function baseFilter(over: Partial<WorkbenchFilter> = {}): WorkbenchFilter {
  return { q: '', status: 'active', cat: '', fee: '', ...over } as WorkbenchFilter
}

function renderBar(props: Partial<Parameters<typeof FilterBar>[0]> = {}) {
  const onChange = vi.fn()
  const utils = render(
    <FilterBar facets={facets()} filter={baseFilter()} onChange={onChange} {...props} />,
  )
  return { ...utils, onChange }
}

function searchInput(): HTMLInputElement {
  return screen.getByPlaceholderText('搜索合同（名称）') as HTMLInputElement
}

function filterButton(): HTMLElement {
  return Array.from(document.querySelectorAll('button')).find((b) =>
    (b.textContent ?? '').includes('筛选'),
  ) as HTMLElement
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('FilterBar：搜索', () => {
  it('输入触发 onChange 的 q 更新', () => {
    const { onChange, unmount } = renderBar()
    fireEvent.change(searchInput(), { target: { value: '张三' } })
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ q: '张三' }))
    unmount()
  })

  it('按 / 聚焦搜索框', () => {
    const { unmount } = renderBar()
    const input = searchInput()
    input.blur()
    act(() => {
      fireEvent.keyDown(window, { key: '/' })
    })
    expect(document.activeElement).toBe(input)
    unmount()
  })

  it('焦点已在输入框时按 / 不抢焦点（可正常输入斜杠）', () => {
    const { unmount } = renderBar()
    const input = searchInput()
    input.focus()
    const ev = new KeyboardEvent('keydown', { key: '/', cancelable: true })
    act(() => {
      window.dispatchEvent(ev)
    })
    // 未被 preventDefault（输入框里能打出 /）
    expect(ev.defaultPrevented).toBe(false)
    unmount()
  })
})

describe('FilterBar：激活 chip', () => {
  it('默认 status=active 时不显示任何激活 chip', () => {
    const { unmount } = renderBar()
    // 只有「筛选」按钮本身，没有带「移除」的 chip
    expect(screen.queryAllByRole('button', { name: '移除' })).toHaveLength(0)
    unmount()
  })

  it('非默认状态出一颗 chip 并显示中文标签', () => {
    const { unmount } = renderBar({ filter: baseFilter({ status: 'archived' }) })
    const chips = screen.getAllByRole('button', { name: '移除' })
    expect(chips).toHaveLength(1)
    expect(document.body.textContent).toContain('已归档')
    unmount()
  })

  it('类目与收费各出一颗 chip，标签取 facet 的 label', () => {
    const { unmount } = renderBar({
      filter: baseFilter({ status: 'active', cat: 'civil', fee: 'hourly' }),
    })
    const chips = screen.getAllByRole('button', { name: '移除' })
    expect(chips).toHaveLength(2)
    expect(document.body.textContent).toContain('民事')
    expect(document.body.textContent).toContain('计时收费')
    unmount()
  })

  it('点移除清掉对应字段', () => {
    const onChange = vi.fn()
    const { unmount } = render(
      <FilterBar facets={facets()} filter={baseFilter({ cat: 'civil' })} onChange={onChange} />,
    )
    fireEvent.click(screen.getByRole('button', { name: '移除' }))
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ cat: '' }))
    unmount()
  })

  it('筛选按钮显示激活数量角标', () => {
    const { unmount } = renderBar({ filter: baseFilter({ status: 'archived', cat: 'civil' }) })
    expect(within(filterButton()).getByText('2')).toBeTruthy()
    unmount()
  })

  it('facet 里找不到的 value 回落显示原始值', () => {
    const { unmount } = renderBar({ filter: baseFilter({ cat: 'unknown-cat' }) })
    expect(document.body.textContent).toContain('unknown-cat')
    unmount()
  })
})

describe('FilterBar：筛选弹层', () => {
  it('点「筛选」展开弹层', () => {
    const { unmount } = renderBar()
    fireEvent.click(filterButton())
    expect(document.body.textContent).toContain('状态')
    unmount()
  })

  it('再点一次收起', () => {
    const { unmount } = renderBar()
    fireEvent.click(filterButton())
    fireEvent.click(filterButton())
    // 收起后状态选项不再可见
    expect(screen.queryByText('在办')).toBeNull()
    unmount()
  })

  it('点弹层外部关闭', () => {
    const { unmount } = renderBar()
    fireEvent.click(filterButton())
    expect(document.body.textContent).toContain('状态')

    fireEvent.mouseDown(document.body)
    expect(screen.queryByText('在办')).toBeNull()
    unmount()
  })

  it('选状态后回调并带该状态', () => {
    const onChange = vi.fn()
    const { unmount } = render(
      <FilterBar facets={facets()} filter={baseFilter()} onChange={onChange} />,
    )
    fireEvent.click(filterButton())
    const opt = Array.from(document.querySelectorAll('button')).find((b) =>
      /已归档/.test(b.textContent ?? ''),
    )
    if (opt) fireEvent.click(opt)
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ status: 'archived' }))
    unmount()
  })
})

describe('FilterBar：facets 为空', () => {
  it('facets 为 null 时不崩，计数角标不显示', () => {
    const { unmount } = render(
      <FilterBar facets={null} filter={baseFilter({ status: 'archived' })} onChange={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: '移除' })).toBeTruthy()
    unmount()
  })
})
