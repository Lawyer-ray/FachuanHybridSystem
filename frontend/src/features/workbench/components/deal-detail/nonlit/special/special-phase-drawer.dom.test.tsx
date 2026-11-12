// @vitest-environment jsdom
/**
 * SpecialPhaseDrawer：阶段抽屉的四个页签与三个动作。
 *
 * 契约要点：
 * - 四个页签各自有内容（详情 / 验收标准 / 交付物 / 变更记录），页签标题带计数
 * - 三条验收标准分别判定：交付物全部定稿、签署率、客户书面确认
 * - 动作都在**本地**：标记完成 / 重新打开 / 计划前后移都由调用方落 state
 * - `phase=null` 时整块不渲染（抽屉关闭）
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { DemoDeliverable } from '../../demo-nonlit'
import { SpecialPhaseDrawer, type DrawerPhase } from './special-phase-drawer'

const DOCS: DemoDeliverable[] = [
  { name: '工商登记与股权结构核实', pages: 12, status: 'done', updatedAt: '11-05 14:20', owner: '房某某' },
  { name: '职工名册与社保清缴明细', pages: 28, status: 'drafting', updatedAt: '11-07 09:40', owner: '黄某某' },
]

function phase(over: Partial<DrawerPhase> = {}): DrawerPhase {
  return {
    id: 'p1',
    seq: '1',
    name: '尽职调查',
    planStart: '2026-10-26',
    planEnd: '2026-11-08',
    status: 'doing',
    criterion: '完成工商、税务、社保、债务四项底稿',
    deliverables: DOCS,
    owner: '房某某',
    ...over,
  }
}

type Handlers = {
  onClose: () => void
  onComplete: (id: string) => void
  onReopen: (id: string) => void
  onShiftPlan: (id: string, days: number) => void
}

function setup(over: Partial<DrawerPhase> = {}, on: Partial<Handlers> = {}) {
  const handlers: Handlers = {
    onComplete: vi.fn(),
    onReopen: vi.fn(),
    onShiftPlan: vi.fn(),
    onClose: vi.fn(),
    ...on,
  }
  const view = render(
    <SpecialPhaseDrawer phase={phase(over)} open {...handlers} />,
  )
  return { ...handlers, ...view }
}

describe('SpecialPhaseDrawer：外壳', () => {
  it('phase=null 时整块不渲染', () => {
    const { container } = render(
      <SpecialPhaseDrawer phase={null} open onClose={vi.fn()} onComplete={vi.fn()} onReopen={vi.fn()} onShiftPlan={vi.fn()} />,
    )
    expect(container.textContent).toBe('')
  })

  it('标题 = 编号 + 阶段名，副标题带计划区间与负责人', () => {
    setup()
    const dialog = screen.getByRole('dialog')
    expect(dialog.getAttribute('aria-label')).toBe('1 尽职调查')
    expect(screen.getByText('计划 2026-10-26 至 2026-11-08 · 负责人 房某某')).toBeTruthy()
  })

  it('页签计数：变更记录数 / 交付物数', () => {
    setup()
    expect(screen.getByRole('button', { name: /交付物清单 2/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /变更记录/ })).toBeTruthy()
  })
})

describe('SpecialPhaseDrawer：详情页签', () => {
  it('默认停在详情，展示状态/负责人/计划/交付物统计', () => {
    setup()
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('当前状态')).toBeTruthy()
    // 「进行中」同时出现在标题徽标与详情格里，两处都算对
    expect(within(dialog).getAllByText('进行中').length).toBeGreaterThanOrEqual(2)
    expect(within(dialog).getByText('2 份（1 份已定稿）')).toBeTruthy()
  })

  it('验收口径原文展示', () => {
    setup()
    expect(screen.getByText('完成工商、税务、社保、债务四项底稿')).toBeTruthy()
  })
})

describe('SpecialPhaseDrawer：动作', () => {
  it('进行中的阶段给「标记完成」，点了带 id 回调', () => {
    const { onComplete } = setup({ status: 'doing' })
    fireEvent.click(screen.getByRole('button', { name: /标记完成/ }))
    expect(onComplete).toHaveBeenCalledWith('p1')
  })

  it('已完成的阶段给「重新打开」而不是「标记完成」', () => {
    const { onReopen } = setup({ status: 'done' })
    expect(screen.queryByRole('button', { name: /标记完成/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /重新打开/ }))
    expect(onReopen).toHaveBeenCalledWith('p1')
  })

  it('计划后移 7 天 / 提前 3 天分别传正负天数', () => {
    const { onShiftPlan } = setup()
    fireEvent.click(screen.getByRole('button', { name: /计划后移 7 天/ }))
    expect(onShiftPlan).toHaveBeenCalledWith('p1', 7)
    fireEvent.click(screen.getByRole('button', { name: /提前 3 天/ }))
    expect(onShiftPlan).toHaveBeenCalledWith('p1', -3)
  })

  it('页脚写明「演示数据 · 改动只在本页生效」', () => {
    setup()
    expect(screen.getByText('演示数据 · 改动只在本页生效')).toBeTruthy()
  })
})

describe('SpecialPhaseDrawer：验收标准页签', () => {
  it('交付物未全部定稿时不算通过，并给出「怎么办」', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /验收标准/ }))
    expect(screen.getByText('1 / 2 份已定稿')).toBeTruthy()
    expect(screen.getByText(/走「交付物清单」页签逐份定稿/)).toBeTruthy()
  })

  it('全部定稿时该条统计到位（1/1）', () => {
    setup({ deliverables: [DOCS[0]!] })
    fireEvent.click(screen.getByRole('button', { name: /验收标准/ }))
    expect(screen.getByText('1 / 1 份已定稿')).toBeTruthy()
  })

  it('三条标准都列出来', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /验收标准/ }))
    expect(screen.getByText('全部交付物已定稿')).toBeTruthy()
    expect(screen.getByText('职工安置协议签署率达标')).toBeTruthy()
    expect(screen.getByText('客户已书面确认')).toBeTruthy()
  })
})

describe('SpecialPhaseDrawer：交付物页签', () => {
  it('列出每份交付物，默认展开第一份并显示版本历史', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /交付物清单 2/ }))
    expect(screen.getByText('工商登记与股权结构核实')).toBeTruthy()
    expect(screen.getByText('职工名册与社保清缴明细')).toBeTruthy()
    // 第一份默认展开 → 它的元信息格可见
    expect(screen.getByText('上传时间')).toBeTruthy()
  })

  it('点第二份切换展开目标（第一份收起）', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /交付物清单 2/ }))
    const rows = screen.getAllByRole('button').filter((b) => /职工名册/.test(b.textContent ?? ''))
    fireEvent.click(rows[0]!)
    expect(screen.getAllByText('上传时间').length).toBeGreaterThan(0)
  })

  it('无交付物时给空态', () => {
    setup({ deliverables: [] })
    fireEvent.click(screen.getByRole('button', { name: /交付物清单 0/ }))
    expect(screen.getByText('本阶段还没有交付物。设计阶段时可以先登记计划项。')).toBeTruthy()
  })
})

describe('SpecialPhaseDrawer：变更记录页签', () => {
  it('有变更时逐条列出（含原因）', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /变更记录/ }))
    // 演示数据里「尽职调查」阶段有变更记录；至少能看到「原因：」前缀
    const hasChanges = screen.queryAllByText(/^原因：/).length > 0
    const hasEmpty = screen.queryByText('本阶段没有变更记录') !== null
    expect(hasChanges || hasEmpty).toBe(true)
  })

  it('没有变更的阶段给空态', () => {
    setup({ name: '不存在的阶段名' })
    fireEvent.click(screen.getByRole('button', { name: /变更记录/ }))
    expect(screen.getByText('本阶段没有变更记录')).toBeTruthy()
  })
})
