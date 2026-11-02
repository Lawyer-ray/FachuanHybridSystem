/**
 * 关厂清盘工作台的展示推导（纯函数，无 DOM、无请求）。
 *
 * 为什么单独成模块：抽屉里要算的几件事（延期几天、整条时间轴怎么缩放、
 * 前置校验过不过、阶段行上挂几条证据）都是**口径**而不是排版。口径写散在
 * 组件里，改一次断点就要翻三个文件；写在测试里能直接钉住。
 *
 * 数据来源一律是 `demo-nonlit.ts` 的 `DEMO_NL1_*` 与本文件传入的阶段列表，
 * 不读后端——关厂清盘的阶段树后端还没有，录屏要的是过程证据，不是实时数据。
 */

import type { DemoNl1DocHistory, DemoNl1GanttRow, DemoNl1GateRule } from '../../demo-nonlit'

/** 抽屉四个页签（阶段详情 / 验收标准 / 交付物 / 变更记录） */
export type SpecialDrawerTab = 'detail' | 'acceptance' | 'docs' | 'changes'

export const SPECIAL_DRAWER_TABS: Array<{ id: SpecialDrawerTab; label: string }> = [
  { id: 'detail', label: '阶段详情' },
  { id: 'acceptance', label: '验收标准' },
  { id: 'docs', label: '交付物清单' },
  { id: 'changes', label: '变更记录' },
]

/** Gantt 行的展示推导结果 */
export interface GanttBar {
  row: DemoNl1GanttRow
  name: string
  seq: string
  status: 'done' | 'doing' | 'todo'
  /** 条形在轨道上的起点（%） */
  left: number
  /** 条形宽度（%）——按「计划工期」占全程的比例 */
  width: number
  /** 相对计划，逾期 / 提前 / 按时（天数） */
  driftDays: number
  drift: 'late' | 'early' | 'ontime'
  /** 结束日（由开始日 + 计划工期推） */
  endDate: string
  startDate: string
}

/** 一组 Gantt 行的整体推导：轨道起点 = 最早开始日，全程 = 最晚结束日 */
export interface GanttChart {
  /** 轨道总天数（至少 1，避免除零） */
  spanDays: number
  startDate: string
  endDate: string
  bars: GanttBar[]
  /** 月刻度（每个自然月的第一天）在轨道上的位置（%） */
  months: Array<{ label: string; left: number }>
}

const MS_PER_DAY = 86_400_000

/** 解析 yyyy-mm-dd 为 UTC 毫秒（不用本地时区：工期按自然日算，与时区无关） */
export function parseDay(text: string): number {
  const [y, m, d] = text.split('-').map(Number)
  if (!y || !m || !d) return Number.NaN
  return Date.UTC(y, m - 1, d)
}

/** UTC 毫秒 → yyyy-mm-dd */
export function formatDay(ms: number): string {
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}`
}

/** 两个 yyyy-mm-dd 之间相差的自然日（end - start） */
export function daysBetween(start: string, end: string): number {
  const a = parseDay(start)
  const b = parseDay(end)
  if (Number.isNaN(a) || Number.isNaN(b)) return 0
  return Math.round((b - a) / MS_PER_DAY)
}

/** 加上 n 天 */
export function addDays(start: string, n: number): string {
  const a = parseDay(start)
  if (Number.isNaN(a)) return ''
  return formatDay(a + n * MS_PER_DAY)
}

/**
 * 生成时间轴：给定阶段列表与 Gantt 行，算出每条的起止与占比。
 *
 * 为什么由「开始日 + 计划工期」推结束日，而不是读阶段自己的 planEnd：
 * 阶段计划会在抽屉里被改，改完要立刻反映到甘特图上，而计划工期是律师
 * 心里的真实口径（「这个阶段要 14 天」）。两者不一致时以工期为准。
 */
export function buildGantt(
  phases: ReadonlyArray<{ id: string; seq: string; name: string; planStart: string; status: 'done' | 'doing' | 'todo' }>,
  rows: readonly DemoNl1GanttRow[],
): GanttChart {
  const byId = new Map(phases.map((p) => [p.id, p]))
  const usable = rows.filter((r) => byId.has(r.phaseId) && byId.get(r.phaseId)!.planStart)
  if (usable.length === 0) return { spanDays: 1, startDate: '', endDate: '', bars: [], months: [] }

  const starts = usable.map((r) => parseDay(byId.get(r.phaseId)!.planStart))
  const ends = usable.map((r, i) => starts[i]! + Math.max(1, r.planDays) * MS_PER_DAY)
  const axisStart = Math.min(...starts)
  const axisEnd = Math.max(...ends)
  const spanDays = Math.max(1, Math.round((axisEnd - axisStart) / MS_PER_DAY))

  const bars: GanttBar[] = usable.map((row, i) => {
    const phase = byId.get(row.phaseId)!
    const start = starts[i]!
    const planDays = Math.max(1, row.planDays)
    const driftDays = row.actualDays > 0 ? row.actualDays - planDays : 0
    const drift: GanttBar['drift'] = driftDays > 0 ? 'late' : driftDays < 0 ? 'early' : 'ontime'
    return {
      row,
      name: phase.name,
      seq: phase.seq,
      status: phase.status,
      left: ((start - axisStart) / MS_PER_DAY / spanDays) * 100,
      width: (planDays / spanDays) * 100,
      driftDays,
      drift,
      startDate: formatDay(start),
      endDate: formatDay(start + planDays * MS_PER_DAY),
    }
  })

  return {
    spanDays,
    startDate: formatDay(axisStart),
    endDate: formatDay(axisEnd),
    bars,
    months: buildMonthTicks(axisStart, axisEnd, spanDays),
  }
}

/** 轨道上的月刻度：只保留与起止不同的整月首日，最多 8 个，过密就隔月取 */
function buildMonthTicks(axisStart: number, axisEnd: number, spanDays: number): Array<{ label: string; left: number }> {
  const ticks: Array<{ label: string; left: number }> = []
  const first = new Date(axisStart)
  let cursor = Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 1)
  while (cursor < axisEnd) {
    const left = ((cursor - axisStart) / MS_PER_DAY / spanDays) * 100
    if (left > 3 && left < 97) {
      const d = new Date(cursor)
      ticks.push({ label: `${d.getUTCMonth() + 1}月`, left })
    }
    const next = new Date(cursor)
    cursor = Date.UTC(next.getUTCFullYear(), next.getUTCMonth() + 1, 1)
  }
  const step = Math.ceil(ticks.length / 8)
  return step > 1 ? ticks.filter((_, i) => i % step === 0) : ticks
}

/** 前置校验结论：3 项里过了几项、能不能推进 */
export interface GateResult {
  total: number
  passed: number
  blocked: number
  /** 首页未通过的规则（确认话术用） */
  firstFailing: DemoNl1GateRule | null
  canAdvance: boolean
}

export function evaluateGate(rules: readonly DemoNl1GateRule[]): GateResult {
  const failing = rules.filter((r) => !r.ok)
  return {
    total: rules.length,
    passed: rules.length - failing.length,
    blocked: failing.length,
    firstFailing: failing[0] ?? null,
    canAdvance: failing.length === 0,
  }
}

/** 交付物版本历史 + 阶段表里的页码，拼出「每份 2-3 版」的完整列表 */
export interface DocVersionRow {
  version: string
  at: string
  who: string
  pages: number
  note: string
  /** 是不是当前版 */
  current: boolean
}

/**
 * 当前版 = 页数等于阶段表 `pages` 的**最后一版**。
 *
 * 不能只比页数就判：修订常常不改页数（v1.2 → v1.3 都是 34 页，只补了签字页），
 * 只比页数会让两版同时标成当前版。取最后一版是因为历史按时间正序登记，
 * 同页数时后登记的那版才是定稿。
 */
export function versionRowsOf(doc: string, history: readonly DemoNl1DocHistory[]): DocVersionRow[] {
  const hit = history.find((h) => h.doc === doc)
  if (!hit) return []
  const lastCurrent = hit.versions.map((v) => v.pages === hit.current).lastIndexOf(true)
  return hit.versions.map((v, i) => ({ ...v, current: i === lastCurrent }))
}

/** 甘特图汇总：几条延期 / 总计划天数 / 整体进度 */
export function ganttSummary(chart: GanttChart): { late: number; planDays: number; progress: number } {
  const planDays = chart.bars.reduce((s, b) => s + b.row.planDays, 0)
  const weighted = chart.bars.reduce((s, b) => s + b.row.planDays * b.row.progress, 0)
  return {
    late: chart.bars.filter((b) => b.drift === 'late').length,
    planDays,
    progress: planDays === 0 ? 0 : Math.round(weighted / planDays),
  }
}
