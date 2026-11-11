// @vitest-environment jsdom
/**
 * PhaseTable：阶段与交付物的真表格（54 号原型第十六～十七轮的最终形态）。
 *
 * 这里锁的是三条**实测踩过的交互坑**：
 * 1. 必须是 `<table>` 且带 colgroup —— 只有 table-layout:fixed 能让日期/交付物/
 *    版本/状态四列在所有层级上对齐（flex/grid 试了 6 种都在 11px 上错开）。
 * 2. 双击阶段名 = 改名；单击阶段名**也要折叠**（但延迟 220ms 以等待可能的第二击）。
 *    曾经的实现直接把名字上的点击放过去，律师点名字完全不折叠。
 * 3. 有 subpath 的交付物才可点开预览；计划项（无文件）不可点。
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PhaseTable } from './PhaseTable'
import type { PhaseNode } from './special-phase-tree'

function node(over: Partial<PhaseNode> = {}): PhaseNode {
  return {
    key: 'ph_1',
    name: '尽职调查',
    acceptance: '',
    open: false,
    startDate: '',
    folders: [],
    deliverables: [],
    ...over,
  }
}

const FILE_DOC = {
  id: 'd1',
  date: '2026-10-03',
  name: '《尽调报告》',
  version: 'v2',
  state: 'ok' as const,
  subpath: 'p/《尽调报告》.pdf',
  planned: false,
}
const PLAN_DOC = {
  id: 'd2',
  date: '',
  name: '《清算方案》',
  version: '',
  state: 'todo' as const,
  planned: true,
}

function setup(tree: PhaseNode[], over: Partial<Parameters<typeof PhaseTable>[0]> = {}) {
  const handlers = {
    fileCountOf: vi.fn(() => 0),
    onToggle: vi.fn(),
    onRename: vi.fn(),
    onOpenDeliverable: vi.fn(),
    onDraft: vi.fn(),
    ...over,
  }
  const view = render(<PhaseTable tree={tree} {...handlers} />)
  return { ...handlers, ...view }
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('表格结构', () => {
  it('是真 <table> 且带 4 列 colgroup（列对齐的前提）', () => {
    const { container } = setup([node()])
    const table = container.querySelector('table')!
    expect(table.tagName).toBe('TABLE')
    expect(table.className).toContain('table-fixed')
    expect(table.querySelectorAll('colgroup col')).toHaveLength(4)
  })

  it('每个阶段一行，带层级属性与展开态', () => {
    const { container } = setup([node({ key: 'ph_a' }), node({ key: 'ph_b' })])
    const rows = container.querySelectorAll('tr[data-phase-row]')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.getAttribute('data-phase-row')).toBe('ph_a')
    expect(rows[0]!.getAttribute('data-depth')).toBe('1')
    expect(rows[0]!.getAttribute('aria-expanded')).toBe('false')
  })

  it('开始日只显示月-日；todo 无日期时日期列显示「未开始」', () => {
    setup([node({ key: 'a', name: '有日期', startDate: '2026-10-26', state: 'doing' }), node({ key: 'b', name: '没日期', state: 'todo' })])
    expect(screen.getByText('10-26')).toBeTruthy()
    // 日期列与右侧状态标签各有一处「未开始」
    expect(screen.getAllByText('未开始').length).toBeGreaterThanOrEqual(2)
  })

  it('文件名行按 id 打标，计划项行加 pending 类', () => {
    const { container } = setup([node({ open: true, deliverables: [FILE_DOC, PLAN_DOC] })])
    const fileRow = container.querySelector('tr[data-file-row="d1"]')!
    const planRow = container.querySelector('tr[data-file-row="d2"]')!
    expect(fileRow.className).not.toContain('pending')
    expect(planRow.className).toContain('pending')
  })
})

describe('折叠 / 展开', () => {
  it('点行内非名字区 → 立刻 onToggle', () => {
    const { onToggle } = setup([node({ deliverables: [FILE_DOC] })])
    const row = document.querySelector('tr[data-phase-row]')!
    fireEvent.click(row.querySelector('td')!)
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('单击阶段名延迟 220ms 后折叠（给双击留出间隔）', () => {
    const { onToggle } = setup([node({ deliverables: [FILE_DOC] })])
    fireEvent.click(screen.getByText('尽职调查'))
    expect(onToggle).not.toHaveBeenCalled()
    act(() => {
      vi.advanceTimersByTime(220)
    })
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('双击阶段名 → 不折叠，进改名态', () => {
    const { onToggle } = setup([node({ deliverables: [FILE_DOC] })])
    const name = screen.getByText('尽职调查')
    fireEvent.click(name)
    fireEvent.click(name) // 第二击取消定时器
    fireEvent.doubleClick(name)
    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(onToggle).not.toHaveBeenCalled()
    expect(document.querySelector('input[autofocus], input')).toBeTruthy()
  })

  it('不可展开的行（无子阶段无交付物）点了也不折叠', () => {
    const { onToggle } = setup([node()])
    fireEvent.click(document.querySelector('tr[data-phase-row] td')!)
    expect(onToggle).not.toHaveBeenCalled()
  })

  it('无子阶段无交付物的行不可展开，因此不会出现「暂无交付物」占位行', () => {
    // `open = p.open && expandable`，而 expandable 在「无子阶段且无交付物」时为 false
    // → 下面那条 `open && files.length === 0 && folders.length === 0` 分支不可达（见报告）
    const { container } = setup([node({ open: true })])
    expect(screen.queryByText('暂无交付物')).toBeNull()
    expect(container.querySelectorAll('tr')).toHaveLength(1)
  })

  it('open=false 时即使有交付物也不渲染文件行', () => {
    const { container } = setup([node({ open: false, deliverables: [FILE_DOC] })])
    expect(container.querySelector('tr[data-file-row]')).toBeNull()
  })
})

describe('改名', () => {
  it('Enter 提交新名字（去首尾空白）', () => {
    const { onRename } = setup([node({ deliverables: [FILE_DOC] })])
    fireEvent.doubleClick(screen.getByText('尽职调查'))
    const input = document.querySelector('input')!
    fireEvent.change(input, { target: { value: '  尽职调查（更新）  ' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onRename).toHaveBeenCalledWith('ph_1', '尽职调查（更新）')
  })

  it('Escape 取消，不提交', () => {
    const { onRename } = setup([node({ deliverables: [FILE_DOC] })])
    fireEvent.doubleClick(screen.getByText('尽职调查'))
    const input = document.querySelector('input')!
    fireEvent.change(input, { target: { value: '不该提交' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onRename).not.toHaveBeenCalled()
    expect(screen.getByText('尽职调查')).toBeTruthy()
  })

  it('空名字不提交（保留原名）', () => {
    const { onRename } = setup([node({ deliverables: [FILE_DOC] })])
    fireEvent.doubleClick(screen.getByText('尽职调查'))
    const input = document.querySelector('input')!
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onRename).not.toHaveBeenCalled()
  })

  it('失焦也提交（律师点开别处不会丢掉改动）', () => {
    const { onRename } = setup([node({ deliverables: [FILE_DOC] })])
    fireEvent.doubleClick(screen.getByText('尽职调查'))
    const input = document.querySelector('input')!
    fireEvent.change(input, { target: { value: '失焦提交' } })
    fireEvent.blur(input)
    expect(onRename).toHaveBeenCalledWith('ph_1', '失焦提交')
  })
})

describe('交付物行', () => {
  it('有 subpath 的可点开预览，参数是整条交付物', () => {
    const { onOpenDeliverable } = setup([node({ open: true, deliverables: [FILE_DOC] })])
    fireEvent.click(screen.getByRole('button', { name: /《尽调报告》/ }))
    expect(onOpenDeliverable).toHaveBeenCalledWith(FILE_DOC)
  })

  it('撰写中（doing）的交付物名后带 ↗ 提示还能改', () => {
    setup([node({ open: true, deliverables: [{ ...FILE_DOC, state: 'doing' }] })])
    expect(screen.getByRole('button', { name: /↗/ })).toBeTruthy()
  })

  it('计划项（无 subpath）不可点，只给悬停说明', () => {
    setup([node({ open: true, deliverables: [PLAN_DOC] })])
    expect(screen.queryByRole('button', { name: /《清算方案》/ })).toBeNull()
    expect(screen.getByTitle('计划中的交付物，还没有文件')).toBeTruthy()
  })

  it('版本号仅在有时渲染；状态文案跟随状态', () => {
    setup([node({ open: true, deliverables: [FILE_DOC, PLAN_DOC] })])
    expect(screen.getByText('v2')).toBeTruthy()
    expect(screen.getByText('定稿')).toBeTruthy()
    expect(screen.getByText('待起草')).toBeTruthy()
  })
})

describe('阶段行动作', () => {
  it('「＋ 起草」停止冒泡，不触发折叠', () => {
    const { onDraft, onToggle } = setup([node({ deliverables: [FILE_DOC] })])
    fireEvent.click(screen.getByRole('button', { name: '＋ 起草' }))
    expect(onDraft).toHaveBeenCalledWith('ph_1')
    expect(onToggle).not.toHaveBeenCalled()
  })

  it('阶段元信息用 fileCountOf 的结果', () => {
    const fileCountOf = vi.fn(() => 3)
    setup([node({ folders: [node({ key: 'child' })] })], { fileCountOf })
    expect(fileCountOf).toHaveBeenCalled()
    expect(screen.getByText('1 个子阶段 · 3 个文件')).toBeTruthy()
  })

  it('状态点按 state 分档（已完成 / 进行中 / 未开始）', () => {
    setup([node({ key: 'a', name: 'A', state: 'done' }), node({ key: 'b', name: 'B', state: 'doing' })])
    expect(screen.getByText('已完成')).toBeTruthy()
    expect(screen.getByText('进行中')).toBeTruthy()
  })

  it('子阶段缩进随层级增加', () => {
    const { container } = setup([node({ key: 'root', folders: [node({ key: 'child', name: '子阶段' })] })])
    const child = container.querySelector('tr[data-phase-row="child"]')!
    expect(child.getAttribute('data-depth')).toBe('2')
  })
})
