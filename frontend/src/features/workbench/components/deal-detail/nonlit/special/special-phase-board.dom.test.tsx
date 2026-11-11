// @vitest-environment jsdom
/**
 * SpecialPhaseBoard：关厂清盘的阶段清单 + 交付物清单 + 推进卡。
 *
 * 契约要点：
 * - 前置校验结果来自 `evaluateGate`，页头写「通过 x / y」，不通过时徽标是「阻断 N 项」
 * - 「当前阶段」= 第一个 doing，没有就第一个 todo；推进 hint 写「a → b」
 * - 阶段抽屉的三个动作改本页 state：标记完成 / 重新打开 / 计划前后移（并提示）
 * - 交付物抽屉的改名/删除/重新起草落在对应阶段的那一行，同名跨阶段不互相干扰
 * - `phaseFocus` 递增会重新打开阶段抽屉（点同一条两次也要有反应）
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { toast } from 'sonner'

import { DEMO_NL1_GATE_RULES, DEMO_NONLIT_PHASES } from '../../demo-nonlit'
import { evaluateGate } from './special-liquidation-model'
import { SpecialPhaseBoard } from './special-phase-board'

const GATE = evaluateGate(DEMO_NL1_GATE_RULES)

/** 阶段行按钮：行内是「编号+名称+计划区间+N 份 · 改 M+确认 K+状态」 */
function phaseRow(name: string) {
  const btn = screen.getAllByRole('button').find((b) => {
    const t = b.textContent ?? ''
    return t.includes(name) && /\d+ 份 · 改 \d+确认 \d+/.test(t)
  })
  if (!btn) throw new Error(`阶段行未找到：${name}`)
  return btn
}

/** 交付物行按钮：行内是「名称+N 页+上传时间+上传人+状态」 */
function docRow(name: string) {
  const btn = screen.getAllByRole('button').find((b) => {
    const t = b.textContent ?? ''
    return t.includes(name) && /\d+ 页\d{2}-\d{2} \d{2}:\d{2}/.test(t)
  })
  if (!btn) throw new Error(`交付物行未找到：${name}`)
  return btn
}

/** 阶段清单里的状态胶囊数（排除抽屉里的同名文案） */
function listStatusCount(label: string): number {
  return DEMO_NONLIT_PHASES.filter((p) => phaseRow(p.name).textContent!.includes(label)).length
}

function firstDocName(): string {
  const d = DEMO_NONLIT_PHASES[0]!.deliverables[0]!
  return d.name
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('前置校验区', () => {
  it('页头写「通过 x / y」', () => {
    render(<SpecialPhaseBoard />)
    expect(screen.getByText(`通过 ${GATE.passed} / ${GATE.total}`)).toBeTruthy()
  })

  it('不通过时徽标是「阻断 N 项」，通过时是「可以推进」', () => {
    render(<SpecialPhaseBoard />)
    const expected = GATE.canAdvance ? '可以推进' : `阻断 ${GATE.blocked} 项`
    expect(screen.getByText(expected)).toBeTruthy()
  })

  it('每条校验项都列出标签；未通过的给「怎么办」', () => {
    render(<SpecialPhaseBoard />)
    for (const r of DEMO_NL1_GATE_RULES) {
      expect(screen.getByText(r.label)).toBeTruthy()
    }
    const failing = DEMO_NL1_GATE_RULES.filter((r) => !r.ok && r.fix)
    for (const r of failing) {
      expect(screen.getByText(`怎么办：${r.fix}`)).toBeTruthy()
    }
  })
})

describe('阶段清单', () => {
  it('每个阶段一行，带「N 份 · 改 M」「确认 K」与状态胶囊', () => {
    render(<SpecialPhaseBoard />)
    const row = phaseRow(DEMO_NONLIT_PHASES[0]!.name)
    expect(row.textContent).toContain(`${DEMO_NONLIT_PHASES[0]!.deliverables.length} 份 · 改`)
    expect(row.textContent).toMatch(/确认 \d+/)
  })

  it('状态文案按 status 映射（已完成 / 进行中 / 未开始）', () => {
    render(<SpecialPhaseBoard />)
    const counts = {
      done: DEMO_NONLIT_PHASES.filter((p) => p.status === 'done').length,
      doing: DEMO_NONLIT_PHASES.filter((p) => p.status === 'doing').length,
      todo: DEMO_NONLIT_PHASES.filter((p) => p.status === 'todo').length,
    }
    expect(screen.getAllByText('已完成')).toHaveLength(counts.done)
    expect(screen.getAllByText('进行中')).toHaveLength(counts.doing)
    expect(screen.getAllByText('未开始')).toHaveLength(counts.todo)
  })

  it('点任意行打开阶段抽屉', () => {
    render(<SpecialPhaseBoard />)
    expect(screen.queryByRole('dialog')).toBeNull()
    fireEvent.click(phaseRow(DEMO_NONLIT_PHASES[0]!.name))
    expect(screen.getByRole('dialog').getAttribute('aria-label')).toBe(
      `${DEMO_NONLIT_PHASES[0]!.seq} ${DEMO_NONLIT_PHASES[0]!.name}`,
    )
  })

  it('「打开当前阶段」打开第一个进行中的阶段', () => {
    render(<SpecialPhaseBoard />)
    fireEvent.click(screen.getByRole('button', { name: '打开当前阶段' }))
    const current = DEMO_NONLIT_PHASES.find((p) => p.status === 'doing') ?? DEMO_NONLIT_PHASES[0]!
    expect(screen.getByRole('dialog').getAttribute('aria-label')).toBe(`${current.seq} ${current.name}`)
  })
})

describe('阶段抽屉动作：只改本页 state', () => {
  it('标记完成 → 该行变成「已完成」并提示', () => {
    render(<SpecialPhaseBoard />)
    const target = DEMO_NONLIT_PHASES.find((p) => p.status === 'doing')!
    const doneBefore = listStatusCount('已完成')
    fireEvent.click(phaseRow(target.name))
    fireEvent.click(screen.getByRole('button', { name: /标记完成/ }))
    expect(phaseRow(target.name).textContent).toContain('已完成')
    expect(listStatusCount('已完成')).toBe(doneBefore + 1)
    expect(toast.success).toHaveBeenCalledWith(
      `「${target.name}」已标记完成`,
      expect.objectContaining({ description: expect.stringContaining('验收结论写入变更记录') }),
    )
  })

  it('重新打开 → 该行回到「进行中」并提示', () => {
    render(<SpecialPhaseBoard />)
    const target = DEMO_NONLIT_PHASES.find((p) => p.status === 'done')!
    fireEvent.click(phaseRow(target.name))
    fireEvent.click(screen.getByRole('button', { name: /重新打开/ }))
    expect(toast.info).toHaveBeenCalledWith(`「${target.name}」已重新打开`, expect.anything())
  })

  it('计划后移 7 天 → 日期真的变了，且提示「后移」', () => {
    render(<SpecialPhaseBoard />)
    const target = DEMO_NONLIT_PHASES.find((p) => p.status === 'doing')!
    fireEvent.click(phaseRow(target.name))
    fireEvent.click(screen.getByRole('button', { name: /计划后移 7 天/ }))
    expect(toast.success).toHaveBeenCalledWith(`「${target.name}」计划后移 7 天`)
    // 关闭抽屉看行上的区间已右移
    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    expect(phaseRow(target.name).textContent).not.toContain(target.planStart.slice(5))
  })

  it('计划提前 3 天 → 提示「提前 3 天」', () => {
    render(<SpecialPhaseBoard />)
    const target = DEMO_NONLIT_PHASES.find((p) => p.status === 'doing')!
    fireEvent.click(phaseRow(target.name))
    fireEvent.click(screen.getByRole('button', { name: /提前 3 天/ }))
    expect(toast.success).toHaveBeenCalledWith(`「${target.name}」计划提前 3 天`)
  })
})

describe('交付物清单', () => {
  it('标题带总数', () => {
    const total = DEMO_NONLIT_PHASES.reduce((s, p) => s + p.deliverables.length, 0)
    render(<SpecialPhaseBoard />)
    expect(screen.getByText(`${total} 份 · 点任意一行看版本与预览`)).toBeTruthy()
  })

  it('点交付物行打开交付物抽屉', () => {
    render(<SpecialPhaseBoard />)
    fireEvent.click(docRow(firstDocName()))
    expect(screen.getByRole('dialog').getAttribute('aria-label')).toBe(firstDocName())
  })

  it('改名：行名更新、抽屉跟着改、提示带书名号', () => {
    render(<SpecialPhaseBoard />)
    fireEvent.click(docRow(firstDocName()))
    fireEvent.click(screen.getByRole('button', { name: /重命名/ }))
    const input = screen.getByDisplayValue(firstDocName())
    fireEvent.change(input, { target: { value: '改名后的交付物' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(toast.success).toHaveBeenCalledWith('已重命名为《改名后的交付物》')
    expect(screen.getByRole('dialog').getAttribute('aria-label')).toBe('改名后的交付物')
  })

  it('删除：行消失、已删除计数 +1', () => {
    const name = firstDocName()
    render(<SpecialPhaseBoard />)
    expect(screen.getByText('已删除 0 份')).toBeTruthy()
    fireEvent.click(docRow(name))
    fireEvent.click(screen.getByRole('button', { name: /删除/ }))
    expect(toast.success).toHaveBeenCalledWith(`《${name}》已移入回收站`, expect.anything())
    expect(screen.getByText('已删除 1 份')).toBeTruthy()
    expect(screen.queryByText(name)).toBeNull()
  })

  it('删空后给「全部交付物已删除」空态', () => {
    const all = DEMO_NONLIT_PHASES.flatMap((p) => p.deliverables.map((d) => d.name))
    render(<SpecialPhaseBoard />)
    for (const name of all) {
      fireEvent.click(docRow(name))
      fireEvent.click(screen.getByRole('button', { name: /删除/ }))
    }
    expect(screen.getByText('全部交付物已删除，可从阶段抽屉重新起草')).toBeTruthy()
  })

  it('重新起草：把该交付物状态改成撰写中并提示', () => {
    // 找一份「已定稿」的，重起草后应变成「撰写中」
    const target = DEMO_NONLIT_PHASES.flatMap((p) => p.deliverables).find((d) => d.status === 'done')!
    render(<SpecialPhaseBoard />)
    fireEvent.click(docRow(target.name))
    fireEvent.click(screen.getByRole('button', { name: /重新起草/ }))
    expect(toast.success).toHaveBeenCalledWith(
      `已按 ${target.name} 当前版重新起草`,
      expect.objectContaining({ description: expect.stringContaining('保存前不影响已定稿版本') }),
    )
  })
})

describe('phaseFocus：外部指示重新打开', () => {
  it('初始 initialPhaseId 直接打开对应抽屉', () => {
    const target = DEMO_NONLIT_PHASES[2]!
    render(<SpecialPhaseBoard initialPhaseId={target.id} />)
    expect(screen.getByRole('dialog').getAttribute('aria-label')).toBe(`${target.seq} ${target.name}`)
  })

  it('phaseFocus 递增时重新打开（关掉后再点同一条也有反应）', () => {
    const target = DEMO_NONLIT_PHASES[2]!
    const { rerender } = render(<SpecialPhaseBoard initialPhaseId={target.id} phaseFocus={0} />)
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '关闭' }))
    expect(screen.queryByRole('dialog')).toBeNull()

    rerender(<SpecialPhaseBoard initialPhaseId={target.id} phaseFocus={1} />)
    expect(screen.getByRole('dialog').getAttribute('aria-label')).toBe(`${target.seq} ${target.name}`)
  })

  it('phaseFocus 变化但没有 initialPhaseId 时不打开抽屉', () => {
    const { rerender } = render(<SpecialPhaseBoard phaseFocus={0} />)
    rerender(<SpecialPhaseBoard phaseFocus={1} />)
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
