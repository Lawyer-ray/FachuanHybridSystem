import { describe, expect, it } from 'vitest'

import { DEMO_NL1_DOC_HISTORY, DEMO_NL1_GANTT, DEMO_NL1_GATE_RULES, DEMO_NONLIT_PHASES } from '../../demo-nonlit'
import {
  addDays,
  buildGantt,
  daysBetween,
  evaluateGate,
  formatDay,
  ganttSummary,
  parseDay,
  versionRowsOf,
} from './special-liquidation-model'

const phases = DEMO_NONLIT_PHASES.map((p) => ({
  id: p.id,
  seq: p.seq,
  name: p.name,
  planStart: p.planStart,
  status: p.status,
}))

describe('日期口径：自然日加减按 UTC 算，不受时区影响', () => {
  it('parseDay / formatDay 往返一致', () => {
    expect(formatDay(parseDay('2026-11-21'))).toBe('2026-11-21')
  })

  it('daysBetween 数的是两端相差的自然日', () => {
    expect(daysBetween('2026-11-21', '2027-01-15')).toBe(55)
    expect(daysBetween('2027-01-15', '2026-11-21')).toBe(-55)
  })

  it('addDays 跨月跨年进位', () => {
    expect(addDays('2026-12-28', 7)).toBe('2027-01-04')
    expect(addDays('2027-01-05', -3)).toBe('2027-01-02')
  })

  it('解析不了给 0 / 空串，不抛错（演示数据可能缺字段）', () => {
    expect(daysBetween('', '2026-01-01')).toBe(0)
    expect(addDays('', 3)).toBe('')
  })
})

describe('buildGantt：7 条阶段摊到一条时间轴上', () => {
  const chart = buildGantt(phases, DEMO_NL1_GANTT)

  it('每条 Gantt 行都对上一个阶段，条形数量与行数相同', () => {
    expect(chart.bars).toHaveLength(DEMO_NL1_GANTT.length)
    expect(chart.bars.map((b) => b.name)).toEqual([
      '尽职调查',
      '方案设计',
      '文件起草',
      '职工安置文书',
      '债权债务与决议',
      '登记与注销',
      '交割与移交',
    ])
  })

  it('起点 = 最早阶段开始日，结束 = 最晚阶段计划结束日', () => {
    expect(chart.startDate).toBe('2026-10-26')
    // 最后一个阶段 2027-04-01 起 30 天
    expect(chart.endDate).toBe('2027-05-01')
    expect(chart.spanDays).toBe(daysBetween('2026-10-26', '2027-05-01'))
  })

  it('首条条形贴左边界，宽度 = 计划工期占全程比例', () => {
    const first = chart.bars[0]!
    expect(first.left).toBe(0)
    expect(first.width).toBeCloseTo((14 / chart.spanDays) * 100, 5)
  })

  it('结束日由开始日 + 计划工期推出，而不是读阶段的 planEnd', () => {
    const p4 = chart.bars.find((b) => b.seq === '4')!
    expect(p4.startDate).toBe('2027-01-16')
    expect(p4.endDate).toBe(addDays('2027-01-16', 74))
  })

  it('延期判定：实际用时超过计划工期才算延期，未开工不判', () => {
    const bySeq = new Map(chart.bars.map((b) => [b.seq, b]))
    expect(bySeq.get('1')!.drift).toBe('early')
    expect(bySeq.get('1')!.driftDays).toBe(-1)
    expect(bySeq.get('3.1')!.drift).toBe('late')
    expect(bySeq.get('3.1')!.driftDays).toBe(11)
    expect(bySeq.get('4')!.driftDays).toBe(0)
    expect(bySeq.get('4')!.row.actualDays).toBe(0)
  })

  it('月刻度只出现在轨道内部，且不超过 8 个', () => {
    expect(chart.months.length).toBeGreaterThan(0)
    expect(chart.months.length).toBeLessThanOrEqual(8)
    chart.months.forEach((m) => {
      expect(m.left).toBeGreaterThan(3)
      expect(m.left).toBeLessThan(97)
    })
  })

  it('阶段列表为空时给安全的空图（不除零）', () => {
    expect(buildGantt([], DEMO_NL1_GANTT)).toEqual({ spanDays: 1, startDate: '', endDate: '', bars: [], months: [] })
  })
})

describe('ganttSummary：延期条数 / 总计划天数 / 加权进度', () => {
  it('按计划工期加权算整体进度，不是简单平均', () => {
    const chart = buildGantt(phases, DEMO_NL1_GANTT)
    const s = ganttSummary(chart)
    expect(s.late).toBe(1)
    expect(s.planDays).toBe(263)
    // 加权：(14*100 + 12*100 + 56*62 + 30*48 + 47*100) / 263
    expect(s.progress).toBe(46)
  })

  it('空图给 0 进度，不出现 NaN', () => {
    expect(ganttSummary(buildGantt([], DEMO_NL1_GANTT))).toEqual({ late: 0, planDays: 0, progress: 0 })
  })
})

describe('evaluateGate：推进前置校验', () => {
  it('3 项里 2 项不过 → 阻断，且给第一条未通过项做确认话术', () => {
    const g = evaluateGate(DEMO_NL1_GATE_RULES)
    expect(g).toMatchObject({ total: 3, passed: 1, blocked: 2, canAdvance: false })
    expect(g.firstFailing?.id).toBe('g2')
  })

  it('全过才允许推进', () => {
    const g = evaluateGate(DEMO_NL1_GATE_RULES.map((r) => ({ ...r, ok: true })))
    expect(g.canAdvance).toBe(true)
    expect(g.blocked).toBe(0)
    expect(g.firstFailing).toBeNull()
  })
})

describe('versionRowsOf：当前版判定', () => {
  it('页数相同不误判两版都是当前版（v1.2 → v1.3 都是 34 页）', () => {
    const rows = versionRowsOf('职工安置方案与补偿测算表', DEMO_NL1_DOC_HISTORY)
    expect(rows.filter((r) => r.current).map((r) => r.version)).toEqual(['v1.3'])
  })

  it('每份交付物的当前版有且只有一个', () => {
    DEMO_NL1_DOC_HISTORY.forEach((h) => {
      const rows = versionRowsOf(h.doc, DEMO_NL1_DOC_HISTORY)
      expect(rows).toHaveLength(h.versions.length)
      expect(rows.filter((r) => r.current)).toHaveLength(1)
    })
  })

  it('没有历史记录的交付物给空数组', () => {
    expect(versionRowsOf('不存在的交付物', DEMO_NL1_DOC_HISTORY)).toEqual([])
  })
})
