// @vitest-environment jsdom
/**
 * PhaseDesignPane：「手工设计」页签（左主线 / 右细节的两栏编辑器）。
 *
 * 契约要点：
 * - 左栏只看主线（编号 + 名称 + 交付物/子阶段计数 + 验收标准 ✓），点行切换选中
 * - 右栏所有结构操作走 special-phase-tree 的纯函数，结果整树交回 onChange
 * - 层级上限 3：到顶时「＋ 在下面加子阶段」消失、「降一级」禁用
 * - 删除有子阶段的节点会先 confirm（不是静默连坐删子树）
 * - 交付物按 id 增删（不用下标）
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

import { toast } from 'sonner'

import { PhaseDesignPane } from './PhaseDesignPane'
import type { PhaseNode } from './special-phase-tree'

function node(over: Partial<PhaseNode> = {}): PhaseNode {
  return { key: 'ph_1', name: '尽职调查', acceptance: '', open: false, startDate: '', folders: [], deliverables: [], ...over }
}

const DOC = {
  id: 'd1',
  date: '2026-10-03',
  name: '《尽调报告》',
  version: 'v2',
  state: 'ok' as const,
  subpath: 'p/a.pdf',
  planned: false,
}

function setup(draft: PhaseNode[], selKey: string | null) {
  const handlers = { onChange: vi.fn(), onSelect: vi.fn() }
  const view = render(<PhaseDesignPane draft={draft} selKey={selKey} {...handlers} />)
  return { ...handlers, ...view }
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('左栏：阶段主线', () => {
  it('空树时给「还没有阶段」', () => {
    setup([], null)
    expect(screen.getByText('还没有阶段')).toBeTruthy()
    // 右栏空态被 <br/> 切成两段，按容器文本匹配
    expect(document.body.textContent).toContain('左侧还没有阶段。')
  })

  it('每行显示序号、名称、交付物数与子阶段数', () => {
    setup(
      [
        node({
          key: 'a',
          name: '尽职调查',
          deliverables: [DOC],
          folders: [node({ key: 'b', name: '工商核查', folders: [] } as Partial<PhaseNode>)],
        }),
      ],
      'a',
    )
    expect(screen.getByText('尽职调查')).toBeTruthy()
    expect(screen.getByText('1 交付物 · 1 子阶段')).toBeTruthy()
  })

  it('未命名阶段显示占位文案', () => {
    setup([node({ key: 'a', name: '' })], null)
    expect(screen.getByText('未命名阶段')).toBeTruthy()
  })

  it('有验收标准时打 ✓ 标记', () => {
    setup([node({ key: 'a', name: 'A', acceptance: '四项底稿齐' })], null)
    expect(screen.getByTitle('已写验收标准')).toBeTruthy()
  })

  it('点行切换选中', () => {
    const { onSelect } = setup([node({ key: 'a', name: 'A' }), node({ key: 'b', name: 'B' })], 'a')
    fireEvent.click(screen.getByText('B'))
    expect(onSelect).toHaveBeenCalledWith('b')
  })

  it('「＋ 阶段」在没有选中时追加到根层，并选中新节点', () => {
    const { onChange, onSelect } = setup([node({ key: 'a', name: 'A' })], null)
    fireEvent.click(screen.getByRole('button', { name: '＋ 阶段' }))
    const next = (onChange as ReturnType<typeof vi.fn>).mock.calls[0]![0] as PhaseNode[]
    expect(next).toHaveLength(2)
    expect(next[1]!.name).toBe('')
    expect(onSelect).toHaveBeenCalledWith(next[1]!.key)
  })

  it('「＋ 阶段」在选中时插到该节点之后（同层）', () => {
    const { onChange } = setup([node({ key: 'a', name: 'A' }), node({ key: 'b', name: 'B' })], 'a')
    fireEvent.click(screen.getByRole('button', { name: '＋ 阶段' }))
    const next = (onChange as ReturnType<typeof vi.fn>).mock.calls[0]![0] as PhaseNode[]
    expect(next.map((n) => n.name)).toEqual(['A', '', 'B'])
  })
})

describe('右栏：选中阶段细节', () => {
  it('显示「第 N 阶段」与层级/上限', () => {
    setup([node({ key: 'a', name: 'A' })], 'a')
    expect(screen.getByText(/第 1 阶段/)).toBeTruthy()
    expect(screen.getByText('1 级 / 最多 3 级')).toBeTruthy()
  })

  it('名称与验收标准都是受控输入，改动整树交回', () => {
    const { onChange } = setup([node({ key: 'a', name: 'A' })], 'a')
    fireEvent.change(screen.getByDisplayValue('A'), { target: { value: '尽调' } })
    const next = (onChange as ReturnType<typeof vi.fn>).mock.calls[0]![0] as PhaseNode[]
    expect(next[0]!.name).toBe('尽调')

    fireEvent.change(screen.getByPlaceholderText('如：《职工安置方案》定稿并经客户书面确认'), {
      target: { value: '四项底稿齐' },
    })
    const next2 = (onChange as ReturnType<typeof vi.fn>).mock.calls.at(-1)![0] as PhaseNode[]
    expect(next2[0]!.acceptance).toBe('四项底稿齐')
  })

  it('同级上移 / 下移调用 moveBy（不动入参）', () => {
    const draft = [node({ key: 'a', name: 'A' }), node({ key: 'b', name: 'B' })]
    const { onChange } = setup(draft, 'b')
    fireEvent.click(screen.getByRole('button', { name: '同级上移' }))
    const next = (onChange as ReturnType<typeof vi.fn>).mock.calls[0]![0] as PhaseNode[]
    expect(next.map((n) => n.name)).toEqual(['B', 'A'])
    expect(draft.map((n) => n.name)).toEqual(['A', 'B'])
  })

  it('第一层时「升一级」禁用；第 3 层时「降一级」禁用且提示达上限', () => {
    setup([node({ key: 'a', name: 'A' })], 'a')
    expect((screen.getByRole('button', { name: '升一级' }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: '降一级（挂到上一个同级阶段下）' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('没有前一个同级时降级 → 只提示原因，不改树', () => {
    const { onChange } = setup([node({ key: 'a', name: 'A' }), node({ key: 'b', name: 'B' })], 'a')
    fireEvent.click(screen.getByRole('button', { name: '降一级（挂到上一个同级阶段下）' }))
    expect(toast.info).toHaveBeenCalledWith('前面没有同级阶段可以挂靠')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('子阶段里有前一个同级时降级成功', () => {
    const { onChange } = setup([node({ key: 'a', name: 'A' }), node({ key: 'b', name: 'B' })], 'b')
    fireEvent.click(screen.getByRole('button', { name: '降一级（挂到上一个同级阶段下）' }))
    const next = (onChange as ReturnType<typeof vi.fn>).mock.calls[0]![0] as PhaseNode[]
    expect(next).toHaveLength(1)
    expect(next[0]!.folders.map((n) => n.name)).toEqual(['B'])
  })

  it('第 3 层节点「＋ 在下面加子阶段」消失，改显示达上限', () => {
    const tree = [node({ key: 'a', name: 'A', folders: [node({ key: 'b', name: 'B', folders: [node({ key: 'c', name: 'C' })] })] })]
    setup(tree, 'c')
    expect(screen.queryByRole('button', { name: '＋ 在下面加子阶段' })).toBeNull()
    expect(screen.getByText('已达 3 级上限')).toBeTruthy()
    expect((screen.getByRole('button', { name: '降一级（挂到上一个同级阶段下）' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('加子阶段：追加到 selected 下并选中它', () => {
    const { onChange, onSelect } = setup([node({ key: 'a', name: 'A' })], 'a')
    fireEvent.click(screen.getByRole('button', { name: '＋ 在下面加子阶段' }))
    const next = (onChange as ReturnType<typeof vi.fn>).mock.calls[0]![0] as PhaseNode[]
    expect(next[0]!.folders).toHaveLength(1)
    expect(onSelect).toHaveBeenCalledWith(next[0]!.folders[0]!.key)
  })

  it('已有子阶段时右栏底部列出子阶段 chip', () => {
    setup([node({ key: 'a', name: 'A', folders: [node({ key: 'b', name: '工商核查' })] })], 'a')
    expect(screen.getByText('子阶段 · 1')).toBeTruthy()
    // 左栏主线行 + 右栏子阶段 chip 各出现一次
    expect(screen.getAllByText('工商核查')).toHaveLength(2)
  })
})

describe('删除', () => {
  it('无子阶段时直接删，选中交给剩下的第一个', () => {
    const { onChange, onSelect } = setup([node({ key: 'a', name: 'A' }), node({ key: 'b', name: 'B' })], 'a')
    fireEvent.click(screen.getByRole('button', { name: '删除阶段' }))
    const next = (onChange as ReturnType<typeof vi.fn>).mock.calls[0]![0] as PhaseNode[]
    expect(next.map((n) => n.name)).toEqual(['B'])
    expect(onSelect).toHaveBeenCalledWith('b')
  })

  it('有子阶段时先 confirm，取消则不删', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const { onChange } = setup([node({ key: 'a', name: 'A', folders: [node({ key: 'b', name: 'B' })] })], 'a')
    fireEvent.click(screen.getByRole('button', { name: '删除阶段' }))
    expect(confirmSpy).toHaveBeenCalledWith('「A」下面还有 1 个子阶段，一起删除？')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('有子阶段时 confirm 确认后连子树删除', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { onChange } = setup([node({ key: 'a', name: 'A', folders: [node({ key: 'b', name: 'B' })] })], 'a')
    fireEvent.click(screen.getByRole('button', { name: '删除阶段' }))
    const next = (onChange as ReturnType<typeof vi.fn>).mock.calls[0]![0] as PhaseNode[]
    expect(next).toEqual([])
  })
})

describe('交付物增删', () => {
  it('空清单时给「还没有交付物」', () => {
    setup([node({ key: 'a', name: 'A' })], 'a')
    expect(screen.getByText('还没有交付物')).toBeTruthy()
  })

  it('已有交付物按状态文案展示，可逐个移除', () => {
    const { onChange } = setup([node({ key: 'a', name: 'A', deliverables: [DOC] })], 'a')
    expect(screen.getByText('《尽调报告》')).toBeTruthy()
    expect(screen.getByText('定稿')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '移除' }))
    const next = (onChange as ReturnType<typeof vi.fn>).mock.calls[0]![0] as PhaseNode[]
    expect(next[0]!.deliverables).toEqual([])
  })

  it('回车添加交付物（自动补书名号）；空输入不提交', () => {
    const { onChange } = setup([node({ key: 'a', name: 'A' })], 'a')
    const input = screen.getByPlaceholderText('《文书名称》，回车添加')
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onChange).not.toHaveBeenCalled()

    fireEvent.change(input, { target: { value: '清算方案' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    const next = (onChange as ReturnType<typeof vi.fn>).mock.calls[0]![0] as PhaseNode[]
    expect(next[0]!.deliverables[0]!.name).toBe('《清算方案》')
  })

  it('「＋」按钮同样添加', () => {
    const { onChange } = setup([node({ key: 'a', name: 'A' })], 'a')
    fireEvent.change(screen.getByPlaceholderText('《文书名称》，回车添加'), { target: { value: '清算方案' } })
    fireEvent.click(screen.getByRole('button', { name: '添加' }))
    expect(onChange).toHaveBeenCalled()
  })
})

describe('嵌套层级展示', () => {
  it('子阶段在主线上缩进且序号是 1.1', () => {
    setup([node({ key: 'a', name: '父', folders: [node({ key: 'b', name: '子' })] })], 'a')
    expect(screen.getByText('1.1')).toBeTruthy()
    // 子节点在主线上的缩进 = (depth-1)*14
    const childRow = screen.getByText('1.1').closest('button') as HTMLElement
    const indent = childRow.querySelector('span') as HTMLElement
    expect(indent.style.width).toBe('14px')
  })
})
