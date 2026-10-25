/**
 * 服务期时间轴测试。
 *
 * 这条轴的价值在**联动**：事项按日落在服务期上，刻度密=那个阶段忙、空档=
 * 服务空转。所以测试重点不是「进度算得准不准」，而是：
 * - 轴外事项被丢弃（否则刻度会画到条外）；
 * - 同一天多个事项聚成一根带 count（否则叠在一起看不出密度）；
 * - 超期/未开始不出负数宽度（进度条不能反向或溢出）。
 */
import { describe, expect, it } from 'vitest'

import { buildTermTimeline, termHeadline, termTone } from './term-timeline'

const BASE = { from: '2026-01-01', to: '2026-12-31' }

describe('buildTermTimeline', () => {
  it('算进度与剩余天数', () => {
    const t = buildTermTimeline({ ...BASE, today: '2026-07-02' })
    expect(t).not.toBeNull()
    expect(t!.daysLeft).toBe(182)
    expect(t!.progress).toBeGreaterThan(0.49)
    expect(t!.progress).toBeLessThan(0.51)
    expect(t!.totalDays).toBe(364)
  })

  it('起止非法时返回 null（不画一条假轴）', () => {
    expect(buildTermTimeline({ from: '2026-12-31', to: '2026-01-01', today: '2026-06-01' })).toBeNull()
    expect(buildTermTimeline({ from: '', to: '', today: '2026-06-01' })).toBeNull()
  })

  it('未开始：进度钳到 0（不能出现负宽度）', () => {
    const t = buildTermTimeline({ ...BASE, today: '2025-06-01' })!
    expect(t.progress).toBe(0)
    expect(t.daysLeft).toBeGreaterThan(0)
  })

  it('已超期：进度钳到 1，剩余为负', () => {
    const t = buildTermTimeline({ ...BASE, today: '2027-03-01' })!
    expect(t.progress).toBe(1)
    expect(t.daysLeft).toBeLessThan(0)
  })

  it('事项落在对应比例位置', () => {
    const t = buildTermTimeline({ ...BASE, today: '2026-07-02', eventDates: ['2026-01-01', '2026-12-31'] })!
    expect(t.ticks).toHaveLength(2)
    expect(t.ticks[0]!.ratio).toBeCloseTo(0, 3)
    expect(t.ticks[1]!.ratio).toBeCloseTo(1, 3)
  })

  it('轴外事项被丢弃（否则刻度画到条外）', () => {
    const t = buildTermTimeline({
      ...BASE,
      today: '2026-07-02',
      eventDates: ['2025-12-31', '2027-01-01', '2026-06-01'],
    })!
    expect(t.ticks).toHaveLength(1)
  })

  it('同一天多个事项聚成一根并记录密度', () => {
    const t = buildTermTimeline({
      ...BASE,
      today: '2026-07-02',
      eventDates: ['2026-03-05', '2026-03-05', '2026-03-05', '2026-08-01'],
    })!
    expect(t.ticks).toHaveLength(2)
    expect(t.ticks[0]!.count).toBe(3)
    expect(t.ticks[1]!.count).toBe(1)
  })

  it('刻度按时间排序（渲染顺序依赖它）', () => {
    const t = buildTermTimeline({
      ...BASE,
      today: '2026-07-02',
      eventDates: ['2026-09-01', '2026-02-01', '2026-05-01'],
    })!
    const ratios = t.ticks.map((x) => x.ratio)
    expect([...ratios].sort((a, b) => a - b)).toEqual(ratios)
  })

  it('标记「今天」那一根刻度', () => {
    const t = buildTermTimeline({ ...BASE, today: '2026-07-02', eventDates: ['2026-07-02'] })!
    expect(t.ticks[0]!.today).toBe(true)
  })

  it('非法日期事项被忽略而不是崩', () => {
    const t = buildTermTimeline({ ...BASE, today: '2026-07-02', eventDates: ['not-a-date', ''] })!
    expect(t.ticks).toHaveLength(0)
  })

  it('预警区从最后 N% 起算', () => {
    const t = buildTermTimeline({ ...BASE, today: '2026-07-02', warnRatio: 0.2 })!
    expect(t.warnFrom).toBeCloseTo(0.8, 5)
    expect(buildTermTimeline({ ...BASE, today: '2026-07-02', warnRatio: 0 })!.warnFrom).toBeNull()
  })
})

describe('termHeadline / termTone', () => {
  it('文案分清还剩 / 今天 / 超期', () => {
    expect(termHeadline(30)).toBe('还剩 30 天')
    expect(termHeadline(0)).toBe('今天到期')
    expect(termHeadline(-5)).toBe('已超期 5 天')
  })

  it('30 天内转提醒色，超期红', () => {
    const mk = (today: string) => buildTermTimeline({ ...BASE, today })!
    expect(termTone(mk('2026-03-01'))).toBe('normal')
    expect(termTone(mk('2026-12-20'))).toBe('warn')
    expect(termTone(mk('2027-01-05'))).toBe('over')
  })
})
