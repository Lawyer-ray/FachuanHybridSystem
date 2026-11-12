// @vitest-environment jsdom
/**
 * TermBar：服务期进度条（把「还剩多少时间」和「这一年忙不忙」画到同一条轴上）。
 *
 * 契约要点：
 * - 刻度语义两种互斥用法：`events`（常法：哪几天有事项）与 `milestones`（专项：
 *   走到第几阶段）；里程碑落在服务期外不画（避免端点外溢出）
 * - 预警区只在「有预警起点且还没走完」时出现
 * - 悬浮文案要能说出「那天发生了什么」，超过 5 条折成「等 N 项」
 * - 服务期非法（to <= from）时整条不渲染
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TermBar } from './TermBar'

const FROM = '2026-01-01'
const TO = '2026-12-31'

function renderBar(over: Partial<Parameters<typeof TermBar>[0]> = {}) {
  return render(<TermBar from={FROM} to={TO} today="2026-06-30" {...over} />)
}

describe('基本渲染', () => {
  it('显示起止、总天数与默认标题', () => {
    renderBar()
    const img = screen.getByRole('img')
    expect(img.getAttribute('aria-label')).toContain('服务期 2026-01-01 至 2026-12-31')
    expect(screen.getByText('2026-01-01 → 2026-12-31')).toBeTruthy()
    // 该行是「共 {t.totalDays} 天」，数字单独成节点 → 用容器文本断言
    expect(document.body.textContent).toContain('共 364 天')
    expect(screen.getAllByText(FROM).length).toBeGreaterThan(0)
    expect(screen.getAllByText(TO).length).toBeGreaterThan(0)
  })

  it('自定义轴标题（专项=项目周期）', () => {
    renderBar({ title: '项目周期' })
    expect(screen.getByText('项目周期')).toBeTruthy()
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('项目周期')
  })

  it('服务期非法（to <= from）时整条不渲染', () => {
    const { container } = render(<TermBar from={TO} to={FROM} today="2026-06-30" />)
    expect(container.textContent).toBe('')
  })

  it('日期解析不了时也不渲染', () => {
    const { container } = render(<TermBar from="nope" to={TO} today="2026-06-30" />)
    expect(container.textContent).toBe('')
  })
})

describe('事项刻度', () => {
  it('同一天的多条事项合并成一个刻度，但计数按实际条数', () => {
    renderBar({
      events: [
        { date: '2026-03-01', title: '租赁合同' },
        { date: '2026-03-01', title: '交接清单' },
        { date: '2026-05-01', title: '开庭' },
      ],
    })
    expect(screen.getByText('2 天有事项 · 共 3 项')).toBeTruthy()
  })

  it('刻度悬浮文案带日期、条数与事项名', () => {
    renderBar({ events: [{ date: '2026-03-01', title: '租赁合同' }, { date: '2026-03-01', title: '交接清单' }] })
    const tick = screen.getByTitle(/2026-03-01 · 2 项/)
    expect(tick.getAttribute('title')).toBe('2026-03-01 · 2 项\n租赁合同、交接清单')
  })

  it('超过 5 条时折成「等 N 项」，不把提示框撑到遮住页面', () => {
    const events = Array.from({ length: 8 }, (_, i) => ({ date: '2026-03-01', title: `事项${i + 1}` }))
    renderBar({ events })
    const title = screen.getByTitle(/2026-03-01 · 8 项/).getAttribute('title')!
    expect(title).toContain('事项1、事项2、事项3、事项4、事项5 等 8 项')
    expect(title).not.toContain('事项6')
  })

  it('纯字符串事项（无标题）只给日期与条数', () => {
    renderBar({ events: ['2026-03-01'] })
    expect(screen.getByTitle('2026-03-01 · 1 项')).toBeTruthy()
  })

  it('没有事项时不显示计数行', () => {
    renderBar()
    expect(screen.queryByText(/天有事项/)).toBeNull()
  })

  it('legend 覆盖默认计数文案', () => {
    renderBar({ events: ['2026-03-01'], legend: '本月已用 12 小时' })
    expect(screen.getByText('本月已用 12 小时')).toBeTruthy()
    expect(screen.queryByText(/天有事项/)).toBeNull()
  })
})

describe('阶段里程碑（专项）', () => {
  const milestones = [
    { date: '2026-02-01', title: '尽职调查', state: 'ok' as const },
    { date: '2026-07-01', title: '文件起草', state: 'doing' as const },
    { date: '2027-03-01', title: '交割', state: 'todo' as const },
  ]

  it('落在服务期内的画出来，期外的不画', () => {
    renderBar({ milestones })
    expect(screen.getByTitle('2026-02-01 · 尽职调查')).toBeTruthy()
    expect(screen.getByTitle('2026-07-01 · 文件起草')).toBeTruthy()
    // 2027-03-01 在服务期外
    expect(screen.queryByTitle('2027-03-01 · 交割')).toBeNull()
  })

  it('日期无法解析的里程碑被跳过', () => {
    renderBar({ milestones: [{ date: 'bad', title: '坏日期', state: 'ok' }] })
    expect(screen.queryByTitle(/坏日期/)).toBeNull()
  })

  it('三种状态用不同边框（已完成实心 / 当前粗环 / 未到虚线）', () => {
    renderBar({ milestones })
    const ok = screen.getByTitle('2026-02-01 · 尽职调查')
    const doing = screen.getByTitle('2026-07-01 · 文件起草')
    expect(ok.className).toContain('bg-muted-foreground/60')
    expect(doing.className).toContain('border-foreground')
    expect(ok.className).not.toBe(doing.className)
  })
})

describe('今天与预警区', () => {
  it('今天在服务期内时画竖线', () => {
    const { container } = renderBar()
    // 竖线是轴上唯一带 bg-status-red 的 span（刻度里的今天是圆点）
    const marks = Array.from(container.querySelectorAll('span')).filter((s) =>
      s.className.includes('bg-status-red'),
    )
    expect(marks.length).toBeGreaterThan(0)
  })

  it('今天已过服务期结束时不再画「今天」竖线', () => {
    const { container } = render(<TermBar from={FROM} to={TO} today="2027-06-01" />)
    const vertical = Array.from(container.querySelectorAll('span')).filter(
      (s) => s.className.includes('bg-status-red') && s.className.includes('w-[2.5px]'),
    )
    expect(vertical).toHaveLength(0)
  })

  it('服务期未走完时显示「到期前 20% 区间」预警区', () => {
    renderBar()
    const warn = screen.getByTitle('到期前 20% 区间') as HTMLElement
    // 起于 80% 处，宽 20%
    expect(warn.style.left).toBe('80%')
    expect(warn.style.width).toBe('20%')
  })

  it('已过服务期（progress = 1）时不再画预警区', () => {
    render(<TermBar from={FROM} to={TO} today="2027-06-01" />)
    expect(screen.queryByTitle('到期前 20% 区间')).toBeNull()
  })
})
