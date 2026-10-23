import { daysFromToday, dealFacts, fmtMoney } from '../../domain'
import type {
  ContractReminder,
  DealCase,
  DealContact,
  DealLogAtt,
  DealParty,
  ReminderOut,
  WorkbenchDeal,
} from '../../types'

/* ============ 程序链 ============ */

/**
 * 程序阶段的程序顺序。后端 CaseStage 枚举的 choices 顺序（一审/二审/执行/劳动仲裁…）不是
 * 程序顺序，合同 representation_stages 也按 choices 序存（322 号存成「一审、二审、劳动仲裁」），
 * 所以排序只能靠这张表：前置程序 → 审判 → 再审/重审分支 → 申诉抗诉 → 执行。未知标签排最后。
 */
export const STAGE_ORDER: readonly string[] = [
  '侦查',
  '审查起诉',
  '劳动仲裁',
  '行政复议',
  '自诉',
  '一审',
  '二审',
  '重审一审',
  '重审二审',
  '申请再审',
  '再审一审',
  '再审二审',
  '提审',
  '死刑复核程序',
  '申诉',
  '申请抗诉',
  '申诉抗诉',
  '执行',
]

function stageRank(stage: string): number {
  const i = STAGE_ORDER.indexOf(stage)
  return i === -1 ? STAGE_ORDER.length : i
}

/** 同阶段内的案件顺序：收案日期升序、同日按 id */
export function orderChain(cases: DealCase[]): DealCase[] {
  return [...cases].sort((a, b) => (a.from || '').localeCompare(b.from || '') || a.id - b.id)
}

export type StepState = 'done' | 'cur' | 'todo'

/**
 * 一个程序阶段节点。cases 可为空（合同勾选了但还没立案 = 未启动）或多个
 * （两个一审分案、按被执行人分立的多个执行 = 分叉）。再往后要长出嵌套（保全挂在一审下、
 * 执行按被执行人再分）时在这里加 children，stepper / 主列都从这棵结构长出来。
 */
export interface StagePlan {
  stage: string
  state: StepState
  cases: DealCase[]
  /** 合同是否勾选了该阶段（未勾选但有案件 = 数据漂移，照样展示） */
  selected: boolean
}

/**
 * 程序计划 = 合同勾选的代理阶段 ∪ 案件实际所在阶段，按程序序排。
 * 合同一个阶段都没勾（库里 45 个争议合同如此）时退化为只看案件。
 */
export function buildStagePlan(selectedStages: string[], cases: DealCase[]): StagePlan[] {
  const byStage = new Map<string, DealCase[]>()
  for (const c of orderChain(cases)) {
    const list = byStage.get(c.proc)
    if (list) list.push(c)
    else byStage.set(c.proc, [c])
  }
  const stages = [...new Set([...selectedStages, ...byStage.keys()])].sort(
    (a, b) => stageRank(a) - stageRank(b) || a.localeCompare(b),
  )
  return stages.map((stage) => {
    const cs = byStage.get(stage) ?? []
    const state: StepState = cs.length === 0 ? 'todo' : cs.every((c) => c.done) ? 'done' : 'cur'
    return { stage, state, cases: cs, selected: selectedStages.includes(stage) }
  })
}

/** 主列案件顺序 = 计划顺序（stepper 就是目录），同阶段内按收案日期 */
export function planCases(plan: StagePlan[]): DealCase[] {
  return plan.flatMap((p) => p.cases)
}

export interface ChainStep {
  key: string
  /** 该阶段首个案件 id；null = 未启动（不可跳转） */
  caseId: number | null
  stage: string
  sub: string
  state: StepState
  /** 该阶段案件数（>1 即分叉，stepper 标 ×N） */
  n: number
}

export function chainSteps(plan: StagePlan[]): ChainStep[] {
  return plan.map((p) => {
    const first = p.cases[0]
    const label = p.state === 'todo' ? '未启动' : p.state === 'done' ? '已结' : '在办'
    return {
      key: p.stage,
      caseId: first?.id ?? null,
      stage: p.stage,
      sub: p.cases.length === 1 && first?.auth ? label + ' · ' + first.auth : label,
      state: p.state,
      n: p.cases.length,
    }
  })
}

/**
 * 「下一步」= 最后一个已启动阶段之后的第一个未启动阶段（全未启动则取第一个）。
 * 夹在中间的未启动阶段（如一审→执行、跳过了勾选的二审）不算下一步，只在 stepper 里如实留空心点。
 */
export function nextStage(plan: StagePlan[]): string | null {
  let lastStarted = -1
  plan.forEach((p, i) => {
    if (p.state !== 'todo') lastStarted = i
  })
  return plan.slice(lastStarted + 1).find((p) => p.state === 'todo')?.stage ?? null
}

/** stepper 右侧摘要：「2 个案件 · 劳动仲裁 → 一审」（只列已有案件的阶段） */
export function chainSummary(plan: StagePlan[]): string {
  const started = plan.filter((p) => p.cases.length > 0)
  if (started.length === 0) return ''
  const n = started.reduce((s, p) => s + p.cases.length, 0)
  return n + ' 个案件 · ' + started.map((p) => p.stage).join(' → ')
}

/** 同阶段多案（分叉）时节标题要带案名才分得清 */
export function ambiguousStages(plan: StagePlan[]): Set<string> {
  return new Set(plan.filter((p) => p.cases.length > 1).map((p) => p.stage))
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

/** 判决书地位顺序：原告系在前、被告系居中、第三人系靠后，执行 / 异议系按裁定书惯例；未知地位殿后保序 */
const STATUS_RANK: string[] = [
  '原告',
  '上诉人',
  '申请人',
  '申请执行人',
  '异议人',
  '被告',
  '被上诉人',
  '被申请人',
  '被执行人',
  '第三人',
  '原审第三人',
  '当事人',
]

/** 诉讼地位行：按地位分组并按判决书逻辑排序（原告 → 被告 → 第三人），无地位的归「当事人」 */
export function legalStatusGroups(c: DealCase): Array<{ status: string; names: string[] }> {
  const groups: Array<{ status: string; names: string[] }> = []
  for (const p of c.parties) {
    if (!p.name) continue
    const status = p.status || '当事人'
    const g = groups.find((x) => x.status === status)
    if (g) g.names.push(p.name)
    else groups.push({ status, names: [p.name] })
  }
  const rank = (status: string) => {
    const i = STATUS_RANK.indexOf(status)
    return i === -1 ? STATUS_RANK.length : i
  }
  // Array.prototype.sort 稳定（ES2019+），未知地位之间保持出现顺序
  return [...groups].sort((a, b) => rank(a.status) - rank(b.status))
}

export interface TimelineEntry {
  key: string
  date: string
  text: string
  who: string
  attN: number
  /** 附件明细（可点预览）；同内容日志合并后为并集，再按文件名去重 */
  atts: DealLogAtt[]
  /** 相同内容自动合并后的条数（>1 显示 ×N） */
  n: number
}

/** 只隐藏「长描述型」括号：案件名在卡片上已有，留着只是冗长；短括号常是区分信息（当事人/年份/备注），必须保留 */
const LONG_PAREN_THRESHOLD = 12

/**
 * 文件名展示形：隐藏括号内冗长的案件背景描述。
 * 「告知书（张某诉某公司买卖合同纠纷一案）_收.pdf」→「告知书_收.pdf」；
 * 「通知书（王某执行案）」「(2026)粤…号」「【发票】某某（个人）」等短括号原样保留——
 * 删掉会让同名文件失去区分度。整名都在括号里时退回原名。
 * 扫描而非正则：案件名里常嵌公司名括号（如「诉某公司（广东）分公司」），需配平。
 */
export function stripEntryParens(name: string): string {
  let out = ''
  let i = 0
  while (i < name.length) {
    const ch = name[i]
    if (ch !== '（' && ch !== '(') {
      out += ch
      i++
      continue
    }
    const open = ch
    const close = ch === '（' ? '）' : ')'
    let depth = 1
    let j = i + 1
    while (j < name.length && depth > 0) {
      if (name[j] === open) depth++
      else if (name[j] === close) depth--
      j++
    }
    if (depth !== 0) {
      out += name.slice(i) // 括号不配对：余下原样保留
      break
    }
    const inner = name.slice(i + 1, j - 1)
    out += inner.trim().length >= LONG_PAREN_THRESHOLD ? '' : name.slice(i, j)
    i = j
  }
  const stripped = out.replace(/\s{2,}/g, ' ').trim()
  if (!stripped) return name
  const stem = stripped.replace(/\.[^.]+$/, '').trim()
  return stem ? stripped : name
}

/**
 * 时间轴按时间升序叙事（抽屉是倒序速览，这里是从头讲到现在）。
 * 相同内容的日志自动合并成一条（测试灌入的重复、短信重放）：条目落在组内
 * 最新一次的位置与时间、who 取最新，附件按 id 去重取并集——真实业务里
 * 同内容不同天的记录（如周期性进度）也只留最新一条叙事，×N 说明发生过几次。
 * 重放日志常带同名不同 id 的重复附件，附件再按文件名去重只展示一个。
 */
export function timelineEntries(c: DealCase): TimelineEntry[] {
  const out: TimelineEntry[] = []
  const byText = new Map<string, TimelineEntry>()
  for (const l of [...c.logs].reverse()) {
    const date = l.when.slice(0, 10)
    const exist = byText.get(l.text)
    if (exist) {
      exist.n += 1
      exist.date = date
      exist.who = l.who || exist.who
      const seenNames = new Set(exist.atts.map((a) => a.name))
      for (const a of l.atts) {
        if (seenNames.has(a.name)) continue
        seenNames.add(a.name)
        exist.atts.push(a)
      }
      exist.attN = exist.atts.length
      continue
    }
    const seenNames = new Set<string>()
    const atts: DealLogAtt[] = []
    for (const a of l.atts) {
      if (!seenNames.has(a.name)) {
        seenNames.add(a.name)
        atts.push(a)
      }
    }
    const entry: TimelineEntry = {
      key: 'L' + l.id,
      date,
      text: l.text,
      who: l.who,
      attN: atts.length,
      atts,
      n: 1,
    }
    byText.set(l.text, entry)
    out.push(entry)
  }
  return out
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

/* ============ 页头 ============ */

/**
 * 页头 meta：类型 · 状态 · 建档编号（空值不渲染）。
 * 我方 → 对方与主办不再出现在页头——右栏「当事人」「办案团队」卡已完整展示，页头重复一遍只会把标题推得更长。
 */
export function headerMetaParts(deal: WorkbenchDeal): MetaPart[] {
  const parts: MetaPart[] = []
  if (deal.ctype) parts.push({ v: deal.ctype, strong: true })
  if (deal.statusLabel) parts.push({ v: deal.statusLabel, strong: true })
  if (deal.filingNo) parts.push({ k: '建档', v: deal.filingNo })
  return parts
}

/** 面包屑短名：全称动辄五六十字会顶满一整行，18 字足够定位；完整名在主标题和 hover title 里 */
/**
 * 附件 chip 的短名：去掉扩展名与第一个「_」起的尾巴。
 * 生成文书的命名是「{文书名}_{委托人相关标识}.ext」（如
 * 民事诉讼风险提示书_test_贵州省山地智能….pdf），chip 只显示文书名——
 * 时间轴里委托人就是本案当事人，尾巴是纯噪音；完整名 hover title 可见。
 * 无下划线的名字只去扩展名；截断后为空（名字以 _ 开头）回退原全名。
 */
export function shortDocName(name: string): string {
  const noExt = name.replace(/\.[a-z0-9]{1,6}$/i, '')
  const cut = noExt.indexOf('_')
  if (cut <= 0) return cut === 0 ? name : noExt
  return noExt.slice(0, cut)
}

/** 日志正文按 URL 切段：text 段原样，url 段渲染成「查看链接」超链接——
 * 法院短信里的送达链接动辄 200+ 字符的 query 串，整串显示既撑版面又没法点。
 * URL 字符集排除 CJK 与中英文括号/句读：短信里链接常紧贴中文，\S 会把
 * 后续文字吞进 URL。
 */
const URL_RE = /https?:\/\/[^\s<>"'（）【】《》「」,。；;、！!？）)]+/g

export type TextSegment = { kind: 'text'; value: string } | { kind: 'url'; value: string }

export function splitLinkText(text: string): TextSegment[] {
  const segments: TextSegment[] = []
  let last = 0
  for (const m of text.matchAll(URL_RE)) {
    const idx = m.index ?? 0
    if (idx > last) segments.push({ kind: 'text', value: text.slice(last, idx) })
    segments.push({ kind: 'url', value: m[0] })
    last = idx + m[0].length
  }
  if (last < text.length) segments.push({ kind: 'text', value: text.slice(last) })
  return segments
}

export function crumbName(name: string, cap = 18): string {
  return name.length > cap ? name.slice(0, cap) + '…' : name
}
