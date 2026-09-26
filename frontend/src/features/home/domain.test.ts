import {
  buildMonthGrid,
  dateKey,
  formatCN,
  formatWeekdayCN,
  parseKey,
  pad2,
  timeOfDay,
  todayKey,
  weekdayColumn,
} from './domain'

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
