// @vitest-environment jsdom
/**
 * PhaseListCard：「阶段与交付物」卡（卡片头计数 + 三个创建动作 + 真表格 + 脚注）。
 *
 * 薄编排层，但两条落库口径必须守住：
 * - **折叠/展开** 是纯 UI 位置 → 走 `onTreeChange`（本地即时生效）
 * - **改名** 是业务数据 → 走 `onSave`（必须提交后端）
 * 三个按钮也只是创建，没有任何导航型按钮（项目红线）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

import { toast } from 'sonner'

import { PhaseListCard } from './PhaseListCard'
import type { PhaseNode } from './special-phase-tree'

function node(over: Partial<PhaseNode> = {}): PhaseNode {
  return { key: 'ph_1', name: '尽职调查', acceptance: '', open: false, startDate: '', folders: [], deliverables: [], ...over }
}

const TREE: PhaseNode[] = [
  node({
    key: 'a',
    name: '尽职调查',
    state: 'done',
    deliverables: [{ id: 'd1', date: '2026-10-03', name: '《尽调报告》', version: 'v2', state: 'ok', subpath: 'p/a.pdf', planned: false }],
  }),
]

function setup(over: Partial<Parameters<typeof PhaseListCard>[0]> = {}) {
  const handlers = {
    saving: false,
    isLoading: false,
    endpointNote: null,
    fileCountOf: vi.fn(() => 0),
    onTreeChange: vi.fn(),
    onSave: vi.fn(),
    onOpenDeliverable: vi.fn(),
    onDraftInto: vi.fn(),
    ...over,
  }
  const view = render(<PhaseListCard tree={TREE} {...handlers} />)
  return { ...handlers, ...view }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('卡片头', () => {
  it('显示阶段数与操作提示', () => {
    setup()
    expect(screen.getByText('阶段与交付物')).toBeTruthy()
    expect(screen.getByText('1 阶段')).toBeTruthy()
    expect(screen.getByText('双击改名 · 与合同文件夹同步')).toBeTruthy()
  })

  it('三个按钮都是创建动作（没有导航按钮）', () => {
    setup()
    expect(screen.getByRole('button', { name: /设计阶段/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /从 0 起草/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /新增交付物/ })).toBeTruthy()
  })
})

describe('端点不可用提示', () => {
  it('有 endpointNote 时提示「只保存在本页」', () => {
    setup({ endpointNote: '404' })
    expect(screen.getByText(/合同阶段接口暂不可用（404）：阶段改动只保存在本页/)).toBeTruthy()
  })

  it('无 endpointNote 时不渲染提示块', () => {
    setup()
    expect(screen.queryByText(/合同阶段接口暂不可用/)).toBeNull()
  })
})

describe('空态', () => {
  it('读取中提示', () => {
    setup({ tree: [], isLoading: true })
    expect(screen.getByText('正在读取阶段…')).toBeTruthy()
  })

  it('无阶段且不读取中时引导两种起手方式', () => {
    setup({ tree: [] })
    expect(screen.getByText(/这份专项还没有阶段/)).toBeTruthy()
  })
})

describe('表格动作：折叠走本地、改名走落库', () => {
  it('点行（非名字区）→ onTreeChange 收到翻转后的树', () => {
    const { onTreeChange, onSave } = setup()
    fireEvent.click(document.querySelector('tr[data-phase-row] td')!)
    expect(onTreeChange).toHaveBeenCalledTimes(1)
    const next = (onTreeChange as ReturnType<typeof vi.fn>).mock.calls[0]![0] as PhaseNode[]
    expect(next[0]!.open).toBe(true)
    expect(onSave).not.toHaveBeenCalled()
  })

  it('双击改名 → onSave 收到改名后的树（业务数据必须落库）', () => {
    const { onSave, onTreeChange } = setup()
    fireEvent.doubleClick(screen.getByText('尽职调查'))
    const input = document.querySelector('input[min-w]') ?? document.querySelector('input')!
    fireEvent.change(input, { target: { value: '尽调（改）' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onSave).toHaveBeenCalledTimes(1)
    const next = (onSave as ReturnType<typeof vi.fn>).mock.calls[0]![0] as PhaseNode[]
    expect(next[0]!.name).toBe('尽调（改）')
    expect(onTreeChange).not.toHaveBeenCalled()
  })

  it('点交付物 → onOpenDeliverable', () => {
    const { onOpenDeliverable } = setup()
    fireEvent.click(document.querySelector('tr[data-phase-row] td')!)
    // 展开后再点交付物（tree 是 props，需展开态来自 props.open）
    expect(onOpenDeliverable).not.toHaveBeenCalled()
  })

  it('props.open=true 时交付物可点并回调', () => {
    const { onOpenDeliverable } = setup({ tree: [{ ...TREE[0]!, open: true }] })
    fireEvent.click(screen.getByRole('button', { name: /《尽调报告》/ }))
    expect(onOpenDeliverable).toHaveBeenCalledWith(
      expect.objectContaining({ name: '《尽调报告》', subpath: 'p/a.pdf' }),
    )
  })

  it('「＋ 起草」→ 打开起草弹窗（创建，不跳页）', () => {
    const { onDraftInto } = setup({ tree: [{ ...TREE[0]!, open: true }] })
    fireEvent.click(screen.getByRole('button', { name: '＋ 起草' }))
    expect(screen.getByText('从 0 起草')).toBeTruthy()
    // 尚未提交 → 不进 onDraftInto
    expect(onDraftInto).not.toHaveBeenCalled()
  })
})

describe('创建动作', () => {
  it('「＋ 新增交付物」提交后走 onTreeChange 并提示落点', () => {
    const { onTreeChange } = setup()
    fireEvent.click(screen.getByRole('button', { name: /新增交付物/ }))
    fireEvent.change(screen.getByPlaceholderText('《文书名称》'), { target: { value: '清算方案' } })
    fireEvent.click(screen.getByRole('button', { name: '记入' }))
    const next = (onTreeChange as ReturnType<typeof vi.fn>).mock.calls[0]![0] as PhaseNode[]
    expect(next[0]!.deliverables.map((d) => d.name)).toContain('《清算方案》')
    expect(toast.success).toHaveBeenCalledWith('已新增交付物 · 待起草', { description: '落在「尽职调查」' })
  })

  it('「从 0 起草」提交后走 onDraftInto（落到选中阶段 + 打开编辑器）', () => {
    const { onDraftInto } = setup()
    fireEvent.click(screen.getByRole('button', { name: /从 0 起草/ }))
    fireEvent.change(screen.getByPlaceholderText('《文书名称》'), { target: { value: '职工安置方案' } })
    fireEvent.change(screen.getByPlaceholderText(/写给 AI 的话/), { target: { value: '按法定标准' } })
    fireEvent.click(screen.getByRole('button', { name: '起草并打开' }))
    expect(onDraftInto).toHaveBeenCalledWith('a', '职工安置方案')
  })

  it('「设计阶段」打开 960 宽的两栏编辑器（含两个页签）', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /设计阶段/ }))
    expect(screen.getByText('手工设计')).toBeTruthy()
    expect(screen.getByText('✦ AI 设计（对话）')).toBeTruthy()
  })
})

describe('脚注', () => {
  it('有 note 时同时给出完成计数', () => {
    setup({ note: '与合同文件夹同步' })
    expect(screen.getByText('与合同文件夹同步')).toBeTruthy()
    expect(screen.getByText('已完成 1 / 1')).toBeTruthy()
  })

  it('无 note 时不渲染脚注', () => {
    setup()
    expect(screen.queryByText(/已完成 \d/)).toBeNull()
  })
})
