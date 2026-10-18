import { LITIGATION_TYPES, daysFromToday, fmtMoney } from '../../domain'
import type { ContractReminder, DealCase, DealContact, ReminderOut, WorkbenchDeal } from '../../types'

/* ============ 程序链 ============ */

/**
 * 程序链排序：按收案日期升序、同日按 id。后端尚未把 previous_case 透出 API
 * （get_case_chain 仅 admin 用），一审→二审→执行的收案时间天然单调，时间序即程序序。
 */
export function orderChain(cases: DealCase[]): DealCase[] {
  return [...cases].sort((a, b) => (a.from || '').localeCompare(b.from || '') || a.id - b.id)
}

export type StepState = 'done' | 'cur' | 'todo'

export interface ChainStep {
  key: string
  /** null = 虚节点（执行未启动） */
  caseId: number | null
  stage: string
  sub: string
  state: StepState
}

/**
 * 「执行」虚节点：有执行程序的争议类型（刑事除外）、链上已有程序、且还没立执行案时显示，
 * 给「＋ 立执行案」一个落点。链为空不显示——没有判决就谈不上执行。
 */
export function needsVirtualExec(caseType: string, ordered: DealCase[]): boolean {
  if (ordered.length === 0) return false
  if (!LITIGATION_TYPES.has(caseType) || caseType === 'criminal') return false
  return !ordered.some((c) => c.proc.includes('执行'))
}

export function chainSteps(ordered: DealCase[], virtualExec: boolean): ChainStep[] {
  const steps: ChainStep[] = ordered.map((c) => ({
    key: 'c' + c.id,
    caseId: c.id,
    stage: c.proc,
    sub: [c.done ? '已结' : '在办', c.auth].filter(Boolean).join(' · '),
    state: c.done ? 'done' : 'cur',
  }))
  if (virtualExec) steps.push({ key: 'exec', caseId: null, stage: '执行', sub: '未启动', state: 'todo' })
  return steps
}

/** stepper 右侧摘要：「2 个案件 · 一审 → 二审」（相邻同阶段合并） */
export function chainSummary(ordered: DealCase[]): string {
  if (ordered.length === 0) return ''
  const stages: string[] = []
  for (const c of ordered) if (stages[stages.length - 1] !== c.proc) stages.push(c.proc)
  return ordered.length + ' 个案件 · ' + stages.join(' → ')
}

/** 同阶段多案（如按被告分立的两个一审）时节标题要带案名才分得清 */
export function ambiguousStages(ordered: DealCase[]): Set<string> {
  const seen = new Map<string, number>()
  for (const c of ordered) seen.set(c.proc, (seen.get(c.proc) ?? 0) + 1)
  return new Set([...seen].filter(([, n]) => n > 1).map(([s]) => s))
}

/* ============ 案件节 ============ */

export interface MetaPart {
  k?: string
  v: string
  strong?: boolean
}

/** 案件 meta 行（空值不渲染）：审理机构 · 收案 · 案由 · 标的 · 保全 */
export function caseMetaParts(c: DealCase): MetaPart[] {
  const parts: MetaPart[] = []
  if (c.auth) parts.push({ v: c.auth, strong: true })
  if (c.from) parts.push({ k: '收案', v: c.from })
  if (c.cause) parts.push({ v: c.cause })
  const target = fmtMoney(c.target)
  if (target) parts.push({ k: '标的', v: target, strong: true })
  const preserv = fmtMoney(c.preserv)
  if (preserv) parts.push({ k: '保全', v: preserv, strong: true })
  return parts
}

/** 诉讼地位行：按地位分组保持出现顺序，无地位的归「当事人」 */
export function legalStatusGroups(c: DealCase): Array<{ status: string; names: string[] }> {
  const groups: Array<{ status: string; names: string[] }> = []
  for (const p of c.parties) {
    if (!p.name) continue
    const status = p.status || '当事人'
    const g = groups.find((x) => x.status === status)
    if (g) g.names.push(p.name)
    else groups.push({ status, names: [p.name] })
  }
  return groups
}

export interface TimelineEntry {
  key: string
  date: string
  text: string
  who: string
  attN: number
}

/** 时间轴按时间升序叙事（抽屉是倒序速览，这里是从头讲到现在） */
export function timelineEntries(c: DealCase): TimelineEntry[] {
  return [...c.logs].reverse().map((l, i) => ({
    key: l.when + '|' + i,
    date: l.when.slice(0, 10),
    text: l.text,
    who: l.who,
    attN: l.attN,
  }))
}

/* ============ 右栏 ============ */

export interface Deadline {
  key: string
  content: string
  typeLabel: string
  /** YYYY-MM-DD */
  due: string
  daysLeft: number
  today: boolean
  /** 所属程序名；合同直挂记「委托」 */
  scope: string
}

interface ReminderLike {
  id: number
  content: string
  reminder_type_label: string
  due_at: string
}

/**
 * 期限三源合流，只取今天及以后（过去的期限是历史，由日志承载）：
 * 合同直挂（ContractOut.reminders）、日志级（CaseOut.logs[].reminders）、
 * 案件直挂（/reminders/list?case_id，开庭多挂这里，带完成态可剔除）。
 */
export function buildDeadlines(
  contractReminders: ContractReminder[],
  ordered: DealCase[],
  caseReminders: ReminderOut[],
  today: Date,
): Deadline[] {
  const procOf = new Map(ordered.map((c) => [c.id, c.proc]))
  const out = new Map<string, Deadline>()
  const add = (r: ReminderLike, scope: string) => {
    const due = r.due_at.slice(0, 10)
    const daysLeft = daysFromToday(due, today)
    if (daysLeft == null || daysLeft < 0) return
    const key = 'r' + r.id
    if (out.has(key)) return
    out.set(key, {
      key,
      content: r.content,
      typeLabel: r.reminder_type_label,
      due,
      daysLeft,
      today: daysLeft === 0,
      scope,
    })
  }
  for (const r of contractReminders) add(r, '委托')
  for (const c of ordered) for (const r of c.logReminders) add(r, c.proc)
  for (const r of caseReminders) {
    if (r.is_completed) continue
    add(r, (r.case != null ? procOf.get(r.case) : undefined) || '案件')
  }
  return [...out.values()].sort((a, b) => a.due.localeCompare(b.due) || a.key.localeCompare(b.key))
}

/** 期限日期短格式：同年只给月-日，跨年带年份（诉讼时效常在数年后） */
export function dueLabel(due: string, today: Date): string {
  return due.slice(0, 4) === String(today.getFullYear()) ? due.slice(5) : due
}

/** 法院联系人按机构分组；没填机构的归到该案审理机构，再退到程序名 */
export function contactGroups(ordered: DealCase[]): Array<{ group: string; rows: DealContact[] }> {
  const groups: Array<{ group: string; rows: DealContact[] }> = []
  for (const c of ordered) {
    for (const t of c.contacts) {
      const name = t.authority || c.auth || c.proc
      const g = groups.find((x) => x.group === name)
      if (g) g.rows.push(t)
      else groups.push({ group: name, rows: [t] })
    }
  }
  return groups
}

/** 右栏「涉案与收费」：标的/保全取链上首个有值的案件，费用取合同（空值不渲染；没金额只有方式时标「收费方式」） */
export function moneyRows(deal: WorkbenchDeal, ordered: DealCase[]): Array<[string, string]> {
  const target = fmtMoney(ordered.map((c) => c.target).find((v) => v != null && v > 0))
  const preserv = fmtMoney(ordered.map((c) => c.preserv).find((v) => v != null && v > 0))
  const fee: [string, string] = deal.amount
    ? ['律师费', deal.amount + (deal.fee ? ' · ' + deal.fee : '')]
    : ['收费方式', deal.fee]
  const rows: Array<[string, string]> = [
    ['标的额', target ?? ''],
    ['保全金额', preserv ?? ''],
    fee,
    ['风险比例', deal.riskRate != null && deal.riskRate !== '' ? deal.riskRate + '%' : ''],
    ['已收款', deal.totalReceived ?? ''],
    ['未收款', deal.unpaid ?? ''],
  ]
  return rows.filter(([, v]) => !!v)
}

/* ============ 页头 ============ */

/** 页头 meta：类型 · 状态 · 我方 → 对方 · 建档编号 · 主办（空值不渲染） */
export function headerMetaParts(deal: WorkbenchDeal): MetaPart[] {
  const parts: MetaPart[] = []
  if (deal.ctype) parts.push({ v: deal.ctype, strong: true })
  if (deal.statusLabel) parts.push({ v: deal.statusLabel, strong: true })
  const ours = deal.partiesAll.filter((p) => p.ours).map((p) => p.name).filter(Boolean)
  const others = deal.partiesAll.filter((p) => !p.ours).map((p) => p.name).filter(Boolean)
  if (ours.length) parts.push({ k: '我方', v: ours.join('、') + (others.length ? ' → ' + others.join('、') : '') })
  if (deal.filingNo) parts.push({ k: '建档', v: deal.filingNo })
  if (deal.primary) parts.push({ k: '主办', v: deal.primary })
  return parts
}
