// @vitest-environment jsdom
/**
 * PhaseCreateDialogs：两个轻量创建弹窗。
 *
 * 契约要点：
 * - 阶段下拉只列**叶子**（起草产出的是具体文书，挂在有子阶段的父节点上没法验收）
 * - 「从 0 起草」三件事必填：目标阶段 / 文书名 / 需求，缺一个就只提示不提交
 * - 「新增交付物」只登记一行计划项；名称或阶段缺一个时提交按钮禁用
 * - 名字统一去首尾空白后再交给调用方
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

import { toast } from 'sonner'

import { PhaseAddDeliverableDialog, PhaseDraftDialog } from './PhaseCreateDialogs'
import type { PhaseNode } from './special-phase-tree'

function node(over: Partial<PhaseNode> = {}): PhaseNode {
  return { key: 'ph_1', name: '尽职调查', acceptance: '', open: false, startDate: '', folders: [], deliverables: [], ...over }
}

/** 一个父阶段 + 两个叶子子阶段（下拉应只出现两个子阶段） */
const TREE: PhaseNode[] = [
  node({
    key: 'root',
    name: '主线',
    folders: [node({ key: 'leaf_a', name: '子阶段 A' }), node({ key: 'leaf_b', name: '子阶段 B' })],
  }),
]

function setupDraft(over: Partial<Parameters<typeof PhaseDraftDialog>[0]> = {}) {
  const handlers = { onTarget: vi.fn(), onOpenChange: vi.fn(), onSubmit: vi.fn() }
  const view = render(
    <PhaseDraftDialog open tree={TREE} targetKey="leaf_a" {...handlers} {...over} />,
  )
  return { ...handlers, ...view }
}

function setupAdd(over: Partial<Parameters<typeof PhaseAddDeliverableDialog>[0]> = {}) {
  const handlers = { onTarget: vi.fn(), onOpenChange: vi.fn(), onSubmit: vi.fn() }
  const view = render(
    <PhaseAddDeliverableDialog open tree={TREE} targetKey="leaf_a" {...handlers} {...over} />,
  )
  return { ...handlers, ...view }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('阶段下拉：只列叶子', () => {
  it('父阶段不入选项，子阶段用「序号 · 名称」展示', () => {
    setupDraft()
    const options = Array.from(document.querySelectorAll('option')).map((o) => o.textContent)
    expect(options).toEqual(['1 · 1 子阶段 A', '1 · 2 子阶段 B'])
    expect(options.some((o) => o?.includes('主线'))).toBe(false)
  })

  it('没有叶子时退回全部节点（不出现空下拉）', () => {
    setupDraft({ tree: [node({ key: 'only', name: '唯一阶段' })] })
    expect(Array.from(document.querySelectorAll('option')).map((o) => o.textContent)).toEqual(['1 唯一阶段'])
  })

  it('value 为空时默认选中第一个可用阶段', () => {
    setupDraft({ targetKey: null })
    expect((document.querySelector('select') as HTMLSelectElement).value).toBe('leaf_a')
  })

  it('改选把新 key 交给 onTarget', () => {
    const { onTarget } = setupDraft()
    fireEvent.change(document.querySelector('select')!, { target: { value: 'leaf_b' } })
    expect(onTarget).toHaveBeenCalledWith('leaf_b')
  })
})

describe('PhaseDraftDialog：从 0 起草', () => {
  it('三项齐全才提交（名字与需求去首尾空白）', () => {
    const { onSubmit } = setupDraft()
    fireEvent.change(screen.getByPlaceholderText('《文书名称》'), { target: { value: '  职工安置方案  ' } })
    fireEvent.change(screen.getByPlaceholderText(/写给 AI 的话/), { target: { value: ' 按法定标准  ' } })
    fireEvent.click(screen.getByRole('button', { name: '起草并打开' }))
    expect(onSubmit).toHaveBeenCalledWith('leaf_a', '职工安置方案')
  })

  it('没选阶段 → 提示，不提交', () => {
    const { onSubmit } = setupDraft({ targetKey: null })
    // targetKey=null 时下拉 value 默认第一个，但提交校验看的是 prop
    fireEvent.change(screen.getByPlaceholderText('《文书名称》'), { target: { value: 'A' } })
    fireEvent.change(screen.getByPlaceholderText(/写给 AI 的话/), { target: { value: 'B' } })
    fireEvent.click(screen.getByRole('button', { name: '起草并打开' }))
    expect(toast.error).toHaveBeenCalledWith('先选一个目标阶段')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('缺文书名 → 提示，不提交', () => {
    const { onSubmit } = setupDraft()
    fireEvent.change(screen.getByPlaceholderText(/写给 AI 的话/), { target: { value: 'B' } })
    fireEvent.click(screen.getByRole('button', { name: '起草并打开' }))
    expect(toast.error).toHaveBeenCalledWith('请填写文书名称')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('缺需求 → 提示，不提交', () => {
    const { onSubmit } = setupDraft()
    fireEvent.change(screen.getByPlaceholderText('《文书名称》'), { target: { value: 'A' } })
    fireEvent.click(screen.getByRole('button', { name: '起草并打开' }))
    expect(toast.error).toHaveBeenCalledWith('请说清楚要起草什么')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('「取消」关闭弹窗、不提交', () => {
    const { onOpenChange, onSubmit } = setupDraft()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('写明会给 AI 带上合同信息（省律师重复交代背景）', () => {
    setupDraft()
    expect(screen.getByText('会给 AI 带上本合同信息，不必重复交代背景。')).toBeTruthy()
  })
})

describe('PhaseAddDeliverableDialog：新增交付物', () => {
  it('名称空时提交按钮禁用', () => {
    setupAdd()
    expect((screen.getByRole('button', { name: '记入' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('没选阶段时也禁用', () => {
    setupAdd({ targetKey: null })
    fireEvent.change(screen.getByPlaceholderText('《文书名称》'), { target: { value: 'A' } })
    expect((screen.getByRole('button', { name: '记入' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('填好后提交（去首尾空白）', () => {
    const { onSubmit } = setupAdd()
    fireEvent.change(screen.getByPlaceholderText('《文书名称》'), { target: { value: '  清算方案  ' } })
    fireEvent.click(screen.getByRole('button', { name: '记入' }))
    expect(onSubmit).toHaveBeenCalledWith('leaf_a', '清算方案')
  })

  it('说明口径：先作计划项入表', () => {
    setupAdd()
    expect(
      screen.getByText('先作为「待起草」的计划项入表；在编辑器里起草或上传文件后才变成实际交付物。'),
    ).toBeTruthy()
  })
})
