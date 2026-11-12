// @vitest-environment jsdom
/**
 * SpecialGanttCard：阶段进度甘特（div 画的条形，不引图表库）。
 *
 * 契约要点：
 * - 一条条形表达三件事：实心段=实际进度、虚线尾=计划内未完成、右上角「延期 N 天」
 * - 延期只有**已开工**的阶段才判（未开工显示「未开工」而不是「延期全期」）
 * - 点任意阶段条把 phaseId 交给调用方（打开该阶段抽屉）
 * - 统计胶囊：总计划天数 / 延期条数 / 整体进度
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DEMO_NL1_GANTT, DEMO_NONLIT_PHASES } from '../../demo-nonlit'
import { buildGantt, ganttSummary } from './special-liquidation-model'
import { SpecialGanttCard } from './special-gantt-card'

const CHART = buildGantt(DEMO_NONLIT_PHASES, DEMO_NL1_GANTT)
const SUM = ganttSummary(CHART)

describe('页头与统计', () => {
  it('显示周期区间与全程天数', () => {
    render(<SpecialGanttCard onPickPhase={vi.fn()} />)
    expect(screen.getByText(`${CHART.startDate} → ${CHART.endDate} · 全程 ${CHART.spanDays} 天`)).toBeTruthy()
  })

  it('三个统计胶囊：总计划 / 延期条数 / 整体进度', () => {
    render(<SpecialGanttCard onPickPhase={vi.fn()} />)
    expect(screen.getByText(`总计划 ${SUM.planDays} 天`)).toBeTruthy()
    expect(screen.getByText(SUM.late > 0 ? `${SUM.late} 条延期` : '无延期')).toBeTruthy()
    expect(screen.getByText(`整体 ${SUM.progress}%`)).toBeTruthy()
  })

  it('时间轴刻度按月显示', () => {
    const { container } = render(<SpecialGanttCard onPickPhase={vi.fn()} />)
    const labels = Array.from(container.querySelectorAll('.absolute.bottom-\\[2px\\]')).map((e) => e.textContent)
    expect(labels).toEqual(CHART.months.map((m) => m.label))
  })
})

describe('条形', () => {
  it('每个阶段一条，title 带编号/名称/区间/计划天数', () => {
    render(<SpecialGanttCard onPickPhase={vi.fn()} />)
    for (const bar of CHART.bars) {
      expect(
        screen.getByTitle(`${bar.seq} ${bar.name} · ${bar.startDate} 至 ${bar.endDate} · 计划 ${bar.row.planDays} 天`),
      ).toBeTruthy()
    }
  })

  it('点任意条把 phaseId 交给调用方', () => {
    const onPickPhase = vi.fn()
    render(<SpecialGanttCard onPickPhase={onPickPhase} />)
    const bar = CHART.bars[0]!
    fireEvent.click(
      screen.getByTitle(`${bar.seq} ${bar.name} · ${bar.startDate} 至 ${bar.endDate} · 计划 ${bar.row.planDays} 天`),
    )
    expect(onPickPhase).toHaveBeenCalledWith(bar.row.phaseId)
  })

  it('延期/提前/按计划各自的读数文案', () => {
    render(<SpecialGanttCard onPickPhase={vi.fn()} />)
    for (const bar of CHART.bars) {
      const expected =
        bar.row.actualDays === 0
          ? '未开工'
          : bar.drift === 'late'
            ? `延期 ${bar.driftDays} 天`
            : bar.drift === 'early'
              ? `提前 ${Math.abs(bar.driftDays)} 天`
              : '按计划'
      expect(screen.getAllByText(expected).length).toBeGreaterThan(0)
    }
  })

  it('进度百分比逐条显示', () => {
    render(<SpecialGanttCard onPickPhase={vi.fn()} />)
    for (const bar of CHART.bars) {
      expect(screen.getAllByText(`${bar.row.progress}%`).length).toBeGreaterThan(0)
    }
  })
})

describe('图例', () => {
  it('四种状态都有图例，并写明可点开抽屉', () => {
    render(<SpecialGanttCard onPickPhase={vi.fn()} />)
    for (const label of ['已完成', '进行中', '延期部分', '未开工']) {
      // 「未开工」也会出现在条形读数上，图例只要求存在
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
    expect(screen.getByText('点任意阶段条可打开阶段抽屉')).toBeTruthy()
  })
})
