import { daysFromToday, dealFacts, fmtMoney } from '../../../domain'
import type {
  ContractReminder,
  DealCase,
  DealContact,
  DealParty,
  ReminderOut,
  WorkbenchDeal,
} from '../../../types'

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
  // 已收/未收不在这组 KV 里：与下方收款列表同卡的「已收 · 已开票 · 未收」
  // 统计条呈现（见 feeStats），避免同一张卡上金额出现两遍。
  const rows: Array<[string, string]> = [
    ['标的额', target ?? ''],
    ['保全金额', preserv ?? ''],
    fee,
    ['风险比例', deal.riskRate != null && deal.riskRate !== '' ? deal.riskRate + '%' : ''],
  ]
  return rows.filter(([, v]) => !!v)
}

/**
 * 收费统计条三格：已收 / 已开票 / 未收。
 *
 * 已收、已开票是「已经发生的钱」，0 也要显式给出（¥0 与「没显示」对财务含义不同）；
 * 未收依赖合同固定金额（风险代理没有「未收」概念），没有就整格不渲染。
 */
export function feeStats(deal: WorkbenchDeal): { received: string; invoiced: string; unpaid: string | null } {
  return {
    received: deal.totalReceived ?? '¥0',
    invoiced: deal.totalInvoiced ?? '¥0',
    unpaid: deal.unpaid,
  }
}

/** 与右栏其他节重复的合同要素：收费方式/风险比例已在「涉案与收费」，代理阶段就是 stepper */
const RAIL_FACT_DROP = new Set(['收费方式', '风险比例', '代理阶段'])

/** 右栏「合同要素」：抽屉同款 dealFacts 去掉同卡重复项 */
export function railFacts(deal: WorkbenchDeal): Array<[string, string]> {
  return dealFacts(deal).filter(([k]) => !RAIL_FACT_DROP.has(k))
}

/** 右栏「当事人」：我方在前；返回首个对方的下标（>0 时该行上方留白断组，不用标签） */
export function railParties(deal: WorkbenchDeal): { rows: DealParty[]; firstOther: number } {
  const rows = [...deal.partiesAll].sort((a, b) => Number(b.ours) - Number(a.ours))
  return { rows, firstOther: rows.findIndex((p) => !p.ours) }
}
