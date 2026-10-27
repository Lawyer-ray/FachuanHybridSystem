import { fmtMoney } from '../../../domain'
import type { DealCase, DealLogAtt } from '../../../types'

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
