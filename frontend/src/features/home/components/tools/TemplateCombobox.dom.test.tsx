// @vitest-environment jsdom
/**
 * TemplateCombobox 测试（jsdom）。
 *
 * 60+ 模板的可搜索组合框。核心不变量：
 * - 搜索同时匹配模板名与分类名，空组被剔除，无匹配给空态
 * - 选中项回显名称并带 aria-selected，未选中回显占位
 * - 点击外部关闭；disabled 不可展开
 * - Enter 在结果唯一时直接选中
 */
import { fireEvent, render, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ConvertTemplateGroup } from '../../api'
import { TemplateCombobox } from './TemplateCombobox'

const GROUPS = [
  {
    category: '民事',
    items: [
      { mbid: 'm1', name: '民事起诉状' },
      { mbid: 'm2', name: '民事答辩状' },
    ],
  },
  {
    category: '刑事',
    items: [{ mbid: 'm3', name: '刑事辩护词' }],
  },
] as unknown as ConvertTemplateGroup[]

function renderCombo(props: Partial<Parameters<typeof TemplateCombobox>[0]> = {}) {
  const onChange = vi.fn()
  const utils = render(
    <TemplateCombobox groups={GROUPS} value="" onChange={onChange} {...props} />,
  )
  const trigger = utils.container.querySelector('[aria-haspopup="listbox"]') as HTMLButtonElement
  return { ...utils, trigger, onChange }
}

function searchBox(): HTMLInputElement {
  return document.querySelector('[aria-label="搜索文书类型"]') as HTMLInputElement
}

describe('TemplateCombobox：折叠态', () => {
  it('未选中时显示占位文案', () => {
    const { container, unmount } = renderCombo()
    expect(container.textContent).toContain('选择文书类型')
    unmount()
  })

  it('已选中时回显模板名称', () => {
    const { container, unmount } = renderCombo({ value: 'm2' })
    expect(within(container).getByText('民事答辩状')).toBeTruthy()
    unmount()
  })

  it('value 不在任何分组内时回显占位', () => {
    const { container, unmount } = renderCombo({ value: 'not-exist' })
    expect(container.textContent).toContain('选择文书类型')
    unmount()
  })

  it('disabled 时点击不展开', () => {
    const { trigger, unmount } = renderCombo({ disabled: true })
    expect(trigger.disabled).toBe(true)
    fireEvent.click(trigger)
    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    unmount()
  })
})

describe('TemplateCombobox：展开', () => {
  it('点击展开，aria-expanded 与 listbox 同步', () => {
    const { trigger, unmount } = renderCombo()
    fireEvent.click(trigger)
    expect(trigger.getAttribute('aria-expanded')).toBe('true')

    const listId = trigger.getAttribute('aria-controls')!
    const list = document.getElementById(listId)
    expect(list).toBeTruthy()
    expect(list!.getAttribute('role')).toBe('listbox')
    unmount()
  })

  it('展开后列出全部模板与分组标题', () => {
    const { trigger, unmount } = renderCombo()
    fireEvent.click(trigger)

    const options = document.querySelectorAll('[role="option"]')
    expect(options).toHaveLength(3)
    expect(document.body.textContent).toContain('民事')
    expect(document.body.textContent).toContain('刑事')
    unmount()
  })

  it('选中项带 aria-selected', () => {
    const { trigger, unmount } = renderCombo({ value: 'm1' })
    fireEvent.click(trigger)

    const selected = Array.from(document.querySelectorAll('[role="option"]')).filter(
      (o) => o.getAttribute('aria-selected') === 'true',
    )
    expect(selected).toHaveLength(1)
    expect(selected[0]!.textContent).toContain('民事起诉状')
    unmount()
  })
})

describe('TemplateCombobox：搜索过滤', () => {
  it('按模板名过滤，空组被剔除', () => {
    const { trigger, unmount } = renderCombo()
    fireEvent.click(trigger)
    fireEvent.change(searchBox(), { target: { value: '起诉' } })

    const options = document.querySelectorAll('[role="option"]')
    expect(options).toHaveLength(1)
    expect(options[0]!.textContent).toContain('民事起诉状')
    unmount()
  })

  it('按分类名过滤：搜「刑事」只剩刑事组', () => {
    const { trigger, unmount } = renderCombo()
    fireEvent.click(trigger)
    fireEvent.change(searchBox(), { target: { value: '刑事' } })

    const options = document.querySelectorAll('[role="option"]')
    expect(options).toHaveLength(1)
    expect(options[0]!.textContent).toContain('刑事辩护词')
    unmount()
  })

  it('无匹配时显示空态，且不声明 listbox 角色', () => {
    const { trigger, unmount } = renderCombo()
    fireEvent.click(trigger)
    fireEvent.change(searchBox(), { target: { value: '不存在的模板' } })

    expect(document.body.textContent).toContain('没有匹配的文书类型')
    const listId = trigger.getAttribute('aria-controls')!
    expect(document.getElementById(listId)!.getAttribute('role')).toBeNull()
    unmount()
  })

  it('清空搜索词恢复全部候选', () => {
    const { trigger, unmount } = renderCombo()
    fireEvent.click(trigger)
    fireEvent.change(searchBox(), { target: { value: '起诉' } })
    expect(document.querySelectorAll('[role="option"]')).toHaveLength(1)

    fireEvent.change(searchBox(), { target: { value: '' } })
    expect(document.querySelectorAll('[role="option"]')).toHaveLength(3)
    unmount()
  })
})

describe('TemplateCombobox：选择与关闭', () => {
  it('点选一项回调 mbid 并收起', () => {
    const { trigger, onChange, unmount } = renderCombo()
    fireEvent.click(trigger)

    const option = Array.from(document.querySelectorAll('[role="option"]')).find((o) =>
      o.textContent?.includes('刑事辩护词'),
    ) as HTMLElement
    fireEvent.click(option)

    expect(onChange).toHaveBeenCalledWith('m3')
    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    unmount()
  })

  it('Enter 在过滤结果唯一时直接选中', () => {
    const { trigger, onChange, unmount } = renderCombo()
    fireEvent.click(trigger)
    fireEvent.change(searchBox(), { target: { value: '辩护' } })
    fireEvent.keyDown(searchBox(), { key: 'Enter' })

    expect(onChange).toHaveBeenCalledWith('m3')
    unmount()
  })

  it('Enter 的「唯一」判据是分组数而非项数（已知语义，记录为现状）', () => {
    // 搜「民事」命中 1 个分组、组内 2 个模板：filtered.length === 1 成立，
    // 于是选中该组第一项。这不是理想语义（用户可能想要第二项），
    // 但属于既有产品行为，测试固化现状以防无意改动。
    const { trigger, onChange, unmount } = renderCombo()
    fireEvent.click(trigger)
    fireEvent.change(searchBox(), { target: { value: '民事' } })
    fireEvent.keyDown(searchBox(), { key: 'Enter' })

    expect(onChange).toHaveBeenCalledWith('m1')
    unmount()
  })

  it('命中多个分组时 Enter 不做选择', () => {
    // 空关键词 → 两个分组 → filtered.length !== 1
    const { trigger, onChange, unmount } = renderCombo()
    fireEvent.click(trigger)
    fireEvent.keyDown(searchBox(), { key: 'Enter' })

    expect(onChange).not.toHaveBeenCalled()
    unmount()
  })

  it('Esc 关闭面板', () => {
    const { trigger, unmount } = renderCombo()
    fireEvent.click(trigger)
    fireEvent.keyDown(searchBox(), { key: 'Escape' })
    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    unmount()
  })

  it('点击外部关闭', () => {
    const { trigger, unmount } = renderCombo()
    fireEvent.click(trigger)
    expect(trigger.getAttribute('aria-expanded')).toBe('true')

    fireEvent.mouseDown(document.body)
    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    unmount()
  })

  it('重新展开会清空上次的搜索词', () => {
    const { trigger, unmount } = renderCombo()
    fireEvent.click(trigger)

    const first = searchBox()
    fireEvent.change(first, { target: { value: '起诉' } })
    fireEvent.mouseDown(document.body)
    fireEvent.click(trigger)

    expect(searchBox().value).toBe('')
    unmount()
  })
})
