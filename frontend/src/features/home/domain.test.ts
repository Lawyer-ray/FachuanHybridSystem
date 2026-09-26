import { describe, expect, it } from 'vitest'

import {
  rangeLabel,
  summaryLine,
  buildMonthGrid,
  computeStats,
  dateKey,
  formatCN,
  formatWeekdayCN,
  groupByDay,
  pad2,
  parseKey,
  timeOfDay,
  toDayEvents,
  todayKey,
  weekdayColumn,
} from './domain'
import type { ReminderOut } from './api'

/** 造一条后端 Reminder（只写用例关心的字段） */
function reminder(over: Partial<ReminderOut> & { due_at: string; reminder_type: string; content: string }): ReminderOut {
  return {
    id: 1,
    contract: null,
    case: null,
    case_log: null,
    reminder_type_label: '',
    metadata: {},
    created_at: '2026-09-01T00:00:00+08:00',
    updated_at: '2026-09-01T00:00:00+08:00',
    ...over,
  }
}

describe('日期工具', () => {
  it('dateKey 用本地时区，不会因 UTC 差一天', () => {
    // 2026-09-17 00:30 本地时间（东八区）若按 toISOString 会变成 09-16
    const d = new Date(2026, 8, 17, 0, 30)
    expect(dateKey(d)).toBe('2026-09-17')
  })

  it('pad2 补零', () => {
    expect(pad2(3)).toBe('03')
    expect(pad2(12)).toBe('12')
  })

  it('timeOfDay 取 HH:mm，无时分给全天', () => {
    expect(timeOfDay('2026-09-28T09:30:00+08:00')).toBe('09:30')
    expect(timeOfDay('2026-09-28T00:00:00+08:00')).toBe('00:00')
    expect(timeOfDay('2026-09-28')).toBe('全天')
  })

  it('weekdayColumn 周一起点：周一=0，周日=6', () => {
    expect(weekdayColumn(new Date(2026, 8, 21))).toBe(0) // 2026-09-21 是周一
    expect(weekdayColumn(new Date(2026, 8, 27))).toBe(6) // 周日
  })

  it('formatCN / formatWeekdayCN', () => {
    expect(formatCN(new Date(2026, 8, 17))).toBe('9 月 17 日')
    expect(formatWeekdayCN(new Date(2026, 8, 17))).toBe('周四')
  })

  it('parseKey 与 dateKey 互逆', () => {
    expect(dateKey(parseKey('2026-09-17'))).toBe('2026-09-17')
  })
})

describe('月历网格', () => {
  it('固定 42 格（6 行），避免切月高度抖动', () => {
    expect(buildMonthGrid(2026, 8)).toHaveLength(42)
    expect(buildMonthGrid(2026, 1)).toHaveLength(42)
  })

  it('首行按周一起点补白：2026-09-01 是周二 → 1 个补白', () => {
    const cells = buildMonthGrid(2026, 8)
    expect(cells[0].inMonth).toBe(false)
    expect(cells[1]).toMatchObject({ day: 1, inMonth: true })
  })

  it('当月天数正确：2026 年 9 月有 30 天', () => {
    const cells = buildMonthGrid(2026, 8)
    const inMonth = cells.filter((c) => c.inMonth)
    expect(inMonth).toHaveLength(30)
    expect(inMonth[0].day).toBe(1)
    expect(inMonth[29].day).toBe(30)
  })

  it('跨年：12 月的补白落到次年 1 月', () => {
    const cells = buildMonthGrid(2026, 11)
    const last = cells[cells.length - 1]
    expect(last.inMonth).toBe(false)
    expect(last.key?.startsWith('2027-01')).toBe(true)
  })
})

describe('事件归一化', () => {
  const today = '2026-09-17'

  it('hearing 归为 court（紧要），期限类归为 deadline', () => {
    const evs = toDayEvents(
      [
        reminder({ id: 1, due_at: '2026-09-21T09:30:00+08:00', reminder_type: 'hearing', content: '开庭 · 第 3 法庭', case: 351 }),
        reminder({ id: 2, due_at: '2026-09-17T23:59:00+08:00', reminder_type: 'evidence_deadline', content: '举证截止' }),
        reminder({ id: 3, due_at: '2026-09-18T10:00:00+08:00', reminder_type: 'other', content: '其它事项' }),
      ],
      today,
    )
    expect(evs.map((e) => e.kind)).toEqual(['deadline', 'follow', 'court'])
    expect(evs.find((e) => e.kind === 'court')?.time).toBe('09:30')
  })

  it('从未知类型兜底为 follow', () => {
    const [e] = toDayEvents(
      [reminder({ due_at: '2026-09-18T10:00:00+08:00', reminder_type: 'weird_type', content: 'X' })],
      today,
    )
    expect(e.kind).toBe('follow')
  })

  it('从 metadata 抽取法庭/时段/律师/案号', () => {
    const [e] = toDayEvents(
      [
        reminder({
          due_at: '2026-10-16T10:00:00+08:00',
          reminder_type: 'hearing',
          content: '某买卖合同案',
          metadata: {
            courtroom: '佛山禅城法院 第三审判庭',
            ajbs: '259820260301031696',
            time_range: '10:00-12:00',
            lawyer_name: '房长波',
            hearing_type: '线下开庭',
          },
        }),
      ],
      today,
    )
    expect(e.place).toBe('佛山禅城法院 第三审判庭')
    expect(e.caseNo).toBe('259820260301031696')
    expect(e.timeRange).toBe('10:00-12:00')
    expect(e.person).toBe('房长波')
    expect(e.hearingType).toBe('线下开庭')
    // 摘要优先「人名 · 地点」，与 admin 的 event-meta 口径一致
    expect(summaryLine(e)).toBe('房长波 · 佛山禅城法院 第三审判庭')
    // 时段起点与开始时刻相同 → rangeLabel 仍返回完整区间，由 UI 决定是否展示
    expect(rangeLabel(e)).toBe('10:00-12:00')
  })

  it('无 source_id 的庭审按「同日同时刻同标题同地点」合并', () => {
    const evs = toDayEvents(
      [
        reminder({
          id: 1,
          due_at: '2026-09-21T09:30:00+08:00',
          reminder_type: 'hearing',
          content: '同一庭',
          metadata: { courtroom: 'A 法庭', lawyer_name: '房长波' },
        }),
        reminder({
          id: 2,
          due_at: '2026-09-21T09:30:00+08:00',
          reminder_type: 'hearing',
          content: '同一庭',
          metadata: { courtroom: 'A 法庭', lawyer_name: '黄崧' },
        }),
        reminder({
          id: 3,
          due_at: '2026-09-21T14:00:00+08:00',
          reminder_type: 'hearing',
          content: '同一庭',
          metadata: { courtroom: 'A 法庭' },
        }),
      ],
      today,
    )
    // 前两条合并，第三条时刻不同不合并
    expect(evs).toHaveLength(2)
    expect(evs[0].person).toBe('房长波、黄崧')
    expect(evs[0].time).toBe('09:30')
    expect(evs[1].time).toBe('14:00')
  })

  it('同一庭、不同 source_id / 案号 / 案名也合并（键用同时刻同法庭）', () => {
    // 真实数据 2026-09-09：4 条记录、2 个案号、2 种案名，其实是同一个庭
    const evs = toDayEvents(
      [
        reminder({
          id: 71,
          due_at: '2026-09-09T06:30:00+00:00',
          reminder_type: 'hearing',
          content: '甲公司与A幕墙公司,王铁鑫房屋租赁合同纠纷一案',
          metadata: { source_id: 'srcA', ajbs: '...8996', courtroom: '高明法院 杨和法庭', time_range: '14:30-15:00', lawyer_name: '黄崧' },
        }),
        reminder({
          id: 72,
          due_at: '2026-09-09T06:30:00+00:00',
          reminder_type: 'hearing',
          content: '甲公司与王铁鑫房屋租赁合同纠纷一案',
          metadata: { source_id: 'srcB', ajbs: '...8997', courtroom: '高明法院 杨和法庭', time_range: '14:30-15:00', lawyer_name: '房长波' },
        }),
        reminder({
          id: 73,
          due_at: '2026-09-09T06:30:00+00:00',
          reminder_type: 'hearing',
          content: '甲公司与王铁鑫房屋租赁合同纠纷一案',
          metadata: { source_id: 'srcB', ajbs: '...8997', courtroom: '高明法院 杨和法庭', time_range: '14:30-15:00', lawyer_name: '黄崧' },
        }),
      ],
      today,
    )
    expect(evs).toHaveLength(1)
    expect(evs[0].person).toBe('黄崧、房长波')   // 两位律师都出现，且去重有序
    expect(evs[0].place).toBe('高明法院 杨和法庭')
  })

  it('没有法庭信息的手工庭不合并（否则同时刻的手工庭会被并成一条）', () => {
    const evs = toDayEvents(
      [
        reminder({ id: 1, due_at: '2026-09-24T09:00:00+08:00', reminder_type: 'hearing', content: '开庭 A 案' }),
        reminder({ id: 2, due_at: '2026-09-24T09:00:00+08:00', reminder_type: 'hearing', content: '开庭 B 案' }),
      ],
      today,
    )
    // metadata 为空 → 拿不到法庭 → 不该合并，宁可重复也不能丢掉一件事
    expect(evs).toHaveLength(2)
  })

  it('同时刻同法庭但不同日不合并', () => {
    const evs = toDayEvents(
      [
        reminder({
          id: 1,
          due_at: '2026-09-09T06:30:00+00:00',
          reminder_type: 'hearing',
          content: '某庭',
          metadata: { courtroom: 'A 法庭', time_range: '14:30-15:00' },
        }),
        reminder({
          id: 2,
          due_at: '2026-09-10T06:30:00+00:00',
          reminder_type: 'hearing',
          content: '某庭',
          metadata: { courtroom: 'A 法庭', time_range: '14:30-15:00' },
        }),
      ],
      today,
    )
    expect(evs).toHaveLength(2)
  })

  it('非庭审（期限/日程）不做合并', () => {
    const evs = toDayEvents(
      [
        reminder({
          id: 1,
          due_at: '2026-09-22T23:59:00+08:00',
          reminder_type: 'evidence_deadline',
          content: '举证截止',
          metadata: { source_id: 'same-source' },
        }),
        reminder({
          id: 2,
          due_at: '2026-09-22T23:59:00+08:00',
          reminder_type: 'evidence_deadline',
          content: '举证截止',
          metadata: { source_id: 'same-source' },
        }),
      ],
      today,
    )
    // reminder_type 不是 hearing，即使 source_id 相同也不合并
    expect(evs).toHaveLength(2)
  })

  it('同一 source_id 但不同日不合并', () => {
    const evs = toDayEvents(
      [
        reminder({
          id: 1,
          due_at: '2026-09-21T09:30:00+08:00',
          reminder_type: 'hearing',
          content: '某庭',
          metadata: { source_id: 'abc' },
        }),
        reminder({
          id: 2,
          due_at: '2026-09-28T09:30:00+08:00',
          reminder_type: 'hearing',
          content: '某庭',
          metadata: { source_id: 'abc' },
        }),
      ],
      today,
    )
    // admin 的合并索引按 day 分桶，这里也必须按天分桶（否则跨天误合并）
    expect(evs).toHaveLength(2)
  })

  it('dueToday 只在当天为 true', () => {
    const evs = toDayEvents(
      [
        reminder({ id: 1, due_at: '2026-09-17T23:59:00+08:00', reminder_type: 'payment_deadline', content: '今天' }),
        reminder({ id: 2, due_at: '2026-09-18T09:00:00+08:00', reminder_type: 'payment_deadline', content: '明天' }),
      ],
      today,
    )
    expect(evs.find((e) => e.title === '今天')?.dueToday).toBe(true)
    expect(evs.find((e) => e.title === '明天')?.dueToday).toBe(false)
  })

  it('按时间升序排列', () => {
    const evs = toDayEvents(
      [
        reminder({ id: 1, due_at: '2026-09-21T14:30:00+08:00', reminder_type: 'other', content: 'B' }),
        reminder({ id: 2, due_at: '2026-09-21T09:30:00+08:00', reminder_type: 'other', content: 'A' }),
      ],
      today,
    )
    expect(evs.map((e) => e.title)).toEqual(['A', 'B'])
  })
})

describe('按日归集', () => {
  it('同一天内紧要事项排前', () => {
    const evs = toDayEvents(
      [
        reminder({ id: 1, due_at: '2026-09-24T16:30:00+08:00', reminder_type: 'other', content: '常规晚' }),
        reminder({ id: 2, due_at: '2026-09-24T23:59:00+08:00', reminder_type: 'appeal_deadline', content: '期限晚' }),
        reminder({ id: 3, due_at: '2026-09-24T10:00:00+08:00', reminder_type: 'hearing', content: '开庭早' }),
      ],
      '2026-09-17',
    )
    const grouped = groupByDay(evs)
    const day = grouped.get('2026-09-24') ?? []
    expect(day.map((e) => e.kind)).toEqual(['court', 'deadline', 'follow'])
  })
})

describe('统计口径', () => {
  const today = '2026-09-17'

  const evs = toDayEvents(
    [
      reminder({ id: 1, due_at: '2026-09-17T23:59:00+08:00', reminder_type: 'evidence_deadline', content: '今天期限' }),
      reminder({ id: 2, due_at: '2026-09-17T09:30:00+08:00', reminder_type: 'hearing', content: '今天开庭' }),
      reminder({ id: 3, due_at: '2026-09-20T09:30:00+08:00', reminder_type: 'hearing', content: '3天后开庭' }),
      reminder({ id: 4, due_at: '2026-09-25T09:30:00+08:00', reminder_type: 'hearing', content: '超7天开庭' }),
      reminder({ id: 5, due_at: '2026-09-28T10:00:00+08:00', reminder_type: 'hearing', content: '本月庭' }),
      reminder({ id: 6, due_at: '2026-09-18T10:00:00+08:00', reminder_type: 'other', content: '常规(不计入)' }),
      reminder({ id: 7, due_at: '2026-10-15T09:00:00+08:00', reminder_type: 'hearing', content: '下月庭' }),
    ],
    today,
  )

  it('今日 = 当天全部条数（含常规）', () => {
    expect(computeStats(evs, today).todayCount).toBe(2)
  })

  it('7 日内到期只算紧要事项，且含今天不含第 8 天', () => {
    // 09-17(1 期限) + 09-17(1 庭) + 09-20(1 庭) = 3；09-25 超窗、09-18 是常规
    expect(computeStats(evs, today).deadlineIn7).toBe(3)
  })

  it('本月庭期只数 court 且同月', () => {
    // 09-17 / 09-20 / 09-25 / 09-28 共 4 个庭；10-15 不算
    expect(computeStats(evs, today).courtThisMonth).toBe(4)
  })

  it('空数据不炸', () => {
    expect(computeStats([], today)).toEqual({ todayCount: 0, deadlineIn7: 0, courtThisMonth: 0 })
  })
})

describe('todayKey', () => {
  it('与 dateKey(new Date()) 一致', () => {
    expect(todayKey()).toBe(dateKey(new Date()))
  })
})
