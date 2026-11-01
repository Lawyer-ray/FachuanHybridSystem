import { describe, expect, it } from 'vitest'

import { DEMO_NL3_MONTHLY_HOURS, DEMO_NL3_RISKS, DEMO_NL3_SERVICE_ITEMS, DEMO_NL3_SERVICE_STATS } from '../../demo-nonlit'
import {
  buildRenewSuggestion,
  effortRows,
  filterItems,
  groupByMonth,
  kindTabs,
  monthBars,
  openHighRiskCount,
  quotaLineRatio,
  quotaTone,
  quotaUsage,
  serviceTermProgress,
} from './advisor-domain'

describe('quotaUsage / quotaTone', () => {
  it('按 本月工时 / 月配额 取整百分比', () => {
    expect(quotaUsage(18.5, 20)).toBe(93)
    expect(quotaUsage(20, 20)).toBe(100)
    expect(quotaUsage(0, 20)).toBe(0)
  })

  it('配额为 0 或负数时不除零', () => {
    expect(quotaUsage(10, 0)).toBe(0)
    expect(quotaUsage(10, -5)).toBe(0)
  })

  it('90% 起标黄、100% 起标红，其余绿', () => {
    expect(quotaTone(89)).toBe('green')
    expect(quotaTone(90)).toBe('yellow')
    expect(quotaTone(99)).toBe('yellow')
    expect(quotaTone(100)).toBe('red')
  })
})

describe('serviceTermProgress', () => {
  it('已用天数 / 合同天数，落在 0–1', () => {
    const p = serviceTermProgress()
    expect(p).toBeCloseTo(DEMO_NL3_SERVICE_STATS.usedDays / DEMO_NL3_SERVICE_STATS.contractDays, 5)
    expect(p).toBeGreaterThan(0)
    expect(p).toBeLessThan(1)
  })
})

describe('monthBars / quotaLineRatio', () => {
  it('柱高取当月在 12 个月里的峰值比例，超配额的月被标出', () => {
    const bars = monthBars(
      [
        { month: '2026-03', hours: 5 },
        { month: '2026-04', hours: 25 },
      ],
      20,
    )
    expect(bars[1]!.ratio).toBe(1)
    expect(bars[0]!.ratio).toBeCloseTo(0.2, 5)
    expect(bars[1]!.over).toBe(true)
    expect(bars[0]!.over).toBe(false)
    expect(bars[0]!.label).toBe('3月')
  })

  it('全部低于配额时，峰值仍取配额本身（柱不会撑满整个高度）', () => {
    const bars = monthBars(
      [
        { month: '2026-03', hours: 4 },
        { month: '2026-04', hours: 10 },
      ],
      20,
    )
    expect(bars[1]!.ratio).toBeCloseTo(0.5, 5)
    expect(quotaLineRatio([{ hours: 4 }, { hours: 10 }], 20)).toBe(1)
  })

  it('没记工时的月保留 2% 的最小柱高', () => {
    const bars = monthBars([{ month: '2026-06', hours: 0 }], 20)
    expect(bars[0]!.ratio).toBe(0.02)
  })
})

describe('effortRows', () => {
  it('明细之和等于工时，不补「其他」', () => {
    const rows = effortRows({
      ...DEMO_NL3_SERVICE_ITEMS[0]!,
      hours: 2.5,
      effort: [
        { label: 'A', hours: 1 },
        { label: 'B', hours: 1.5 },
      ],
    })
    expect(rows).toHaveLength(2)
  })

  it('明细不足时补一条「沟通与归档」把差额补齐', () => {
    const rows = effortRows({
      ...DEMO_NL3_SERVICE_ITEMS[0]!,
      hours: 2,
      effort: [{ label: 'A', hours: 1.2 }],
    })
    expect(rows.at(-1)).toEqual({ label: '沟通与归档', hours: 0.8 })
    expect(rows.reduce((s, r) => s + r.hours, 0)).toBeCloseTo(2, 5)
  })

  it('演示数据里每条事项的明细都对得上工时', () => {
    for (const it of DEMO_NL3_SERVICE_ITEMS) {
      const sum = it.effort.reduce((s, e) => s + e.hours, 0)
      expect(sum).toBeCloseTo(it.hours, 5)
    }
  })
})

describe('kindTabs / filterItems', () => {
  const tabs = kindTabs(DEMO_NL3_SERVICE_ITEMS)

  it('首个 tab 是「全部」，条数与工时等于全量', () => {
    expect(tabs[0]!.key).toBe('all')
    expect(tabs[0]!.count).toBe(DEMO_NL3_SERVICE_ITEMS.length)
    expect(tabs[0]!.hours).toBeCloseTo(
      Math.round(DEMO_NL3_SERVICE_ITEMS.reduce((s, i) => s + i.hours, 0) * 10) / 10,
      5,
    )
  })

  it('每个类型的条数与工时小计都对得上明细', () => {
    const contract = tabs.find((t) => t.key === '合同审查')!
    expect(contract.count).toBe(DEMO_NL3_SERVICE_ITEMS.filter((i) => i.kind === '合同审查').length)
    expect(contract.hours).toBeCloseTo(
      DEMO_NL3_SERVICE_ITEMS.filter((i) => i.kind === '合同审查').reduce((s, i) => s + i.hours, 0),
      5,
    )
  })

  it('各 tab 的工时小计之和等于全部', () => {
    const sum = tabs
      .filter((t) => t.key !== 'all')
      .reduce((s, t) => s + t.hours, 0)
    expect(sum).toBeCloseTo(tabs[0]!.hours, 1)
  })

  it('filterItems：all 不过滤，具体类型只留该类型', () => {
    expect(filterItems(DEMO_NL3_SERVICE_ITEMS, 'all')).toHaveLength(DEMO_NL3_SERVICE_ITEMS.length)
    const consults = filterItems(DEMO_NL3_SERVICE_ITEMS, '咨询')
    expect(consults.length).toBeGreaterThan(0)
    expect(consults.every((i) => i.kind === '咨询')).toBe(true)
  })
})

describe('groupByMonth', () => {
  it('按 yyyy-mm 连续分组，组内顺序不变', () => {
    const groups = groupByMonth(DEMO_NL3_SERVICE_ITEMS)
    expect(groups.map((g) => g.month)).toEqual(['2026-11', '2026-10', '2026-09'])
    expect(groups[0]!.items[0]!.date.startsWith('2026-11')).toBe(true)
    expect(groups.reduce((s, g) => s + g.items.length, 0)).toBe(DEMO_NL3_SERVICE_ITEMS.length)
  })
})

describe('buildRenewSuggestion', () => {
  it('到期在即 + 配额吃紧 + 高风险未闭环 → 调价续签，报价按 1.2 系数上浮', () => {
    const s = buildRenewSuggestion({ remainDays: 60, usedHours: 18.5, monthlyQuota: 20, baseFee: 96000, highRiskOpen: 2 })
    expect(s.verdict).toBe('renegotiate')
    expect(s.suggestedFee).toBe(115200)
    expect(s.signals.find((x) => x.key === 'term')!.tone).toBe('yellow')
    expect(s.signals.find((x) => x.key === 'quota')!.value).toBe('93%')
  })

  it('剩余 30 天内标红', () => {
    const s = buildRenewSuggestion({ remainDays: 20, usedHours: 10, monthlyQuota: 20, highRiskOpen: 0 })
    expect(s.signals.find((x) => x.key === 'term')!.tone).toBe('red')
  })

  it('用量不足且未进续签窗口 → 建议暂缓、报价不变', () => {
    const s = buildRenewSuggestion({ remainDays: 200, usedHours: 6, monthlyQuota: 20, baseFee: 96000, highRiskOpen: 0 })
    expect(s.verdict).toBe('hold')
    expect(s.suggestedFee).toBe(96000)
    expect(s.signals.find((x) => x.key === 'demand')!.value).toBe('偏低')
  })

  it('用量低但已进续签窗口 → 不判暂缓（低用量只是谈配额的筹码）', () => {
    const s = buildRenewSuggestion({ remainDays: 60, usedHours: 6, monthlyQuota: 20, highRiskOpen: 0 })
    expect(s.verdict).toBe('renew')
    expect(s.suggestedFee).toBe(105600)
  })

  it('全部正常 → 原价续签', () => {
    const s = buildRenewSuggestion({ remainDays: 120, usedHours: 15, monthlyQuota: 20, baseFee: 96000, highRiskOpen: 0 })
    expect(s.verdict).toBe('renew')
    expect(s.title).toBe('建议原价续签')
    expect(s.suggestedFee).toBe(105600)
    expect(s.signals.find((x) => x.key === 'term')!.tone).toBe('green')
    expect(s.signals.find((x) => x.key === 'risk')!.tone).toBe('green')
  })

  it('建议动作随结论变化，且每个结论都有可执行动作', () => {
    const cases = [
      { verdict: 'renew', remainDays: 200, usedHours: 15, highRiskOpen: 0 },
      { verdict: 'hold', remainDays: 200, usedHours: 4, highRiskOpen: 0 },
      { verdict: 'renegotiate', remainDays: 60, usedHours: 19, highRiskOpen: 1 },
    ] as const
    for (const c of cases) {
      const s = buildRenewSuggestion({ ...c, monthlyQuota: 20 })
      expect(s.verdict).toBe(c.verdict)
      expect(s.actions.length).toBeGreaterThanOrEqual(3)
      expect(s.headline.length).toBeGreaterThan(0)
    }
  })

  it('不传参数时按演示数据生成，并能在报价里看到「元」', () => {
    const s = buildRenewSuggestion()
    expect(s.signals).toHaveLength(4)
    expect(s.headline).toContain('元')
    expect(s.verdict).toBe('renegotiate')
  })
})

describe('openHighRiskCount', () => {
  it('只数「高」等级且未闭环的条目', () => {
    const expected = DEMO_NL3_RISKS.filter((r) => r.level === '高' && !r.closed).length
    expect(openHighRiskCount()).toBe(expected)
    expect(openHighRiskCount()).toBeGreaterThan(0)
  })
})

describe('演示数据自洽', () => {
  it('月度工时里 11 月等于本月工时、10 月与 9 月等于事项明细合计', () => {
    const byMonth = (m: string) =>
      DEMO_NL3_MONTHLY_HOURS.find((x) => x.month === m)!.hours
    expect(byMonth('2026-11')).toBeCloseTo(DEMO_NL3_SERVICE_STATS.totalHours, 5)
    for (const month of ['2026-10', '2026-09']) {
      const sum = DEMO_NL3_SERVICE_ITEMS.filter((i) => i.date.startsWith(month)).reduce((s, i) => s + i.hours, 0)
      expect(byMonth(month)).toBeCloseTo(sum, 5)
    }
  })

  it('事项跨 3 个月、共 16 条，风险清单覆盖三类', () => {
    expect(DEMO_NL3_SERVICE_ITEMS).toHaveLength(16)
    expect(new Set(DEMO_NL3_SERVICE_ITEMS.map((i) => i.date.slice(0, 7))).size).toBe(3)
    expect(new Set(DEMO_NL3_RISKS.map((r) => r.category))).toEqual(new Set(['合同到期', '用工风险', '合规缺口']))
  })
})
