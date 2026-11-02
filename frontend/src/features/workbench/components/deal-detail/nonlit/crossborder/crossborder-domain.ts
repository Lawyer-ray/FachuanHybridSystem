import type { DemoContractRevision, DemoNl2Clause } from '../../demo-nonlit'

/**
 * 跨境审查工作台的纯逻辑：筛选口径、双语修订红线接通、逐条采纳的推进。
 *
 * 抽出来是因为这三件事都有「看起来对、录屏时才发现错」的边界：
 *   · 筛选 tab 的计数与过滤结果必须是同一个来源，否会出现「高 2」却筛出 3 条
 *   · 双栏对齐靠「一句话等于一个挂载点」，左右段数不一致就会错行
 *   · 逐条采纳走到最后一条必须收尾，不能停在「第 6 / 5 条」
 */

/** 顶部审查维度 tab */
export interface ReviewFilterTab {
  id: string
  label: string
  revIds: string[]
}

/** tab 标题带计数：[全部 5] [高 2] … */
export function filterTabLabel(tab: ReviewFilterTab, total: number): string {
  const n = tab.revIds.length > 0 ? tab.revIds.length : total
  return `${tab.label} ${n}`
}

/** 按 tab 过滤修订清单；revIds 为空视为不筛选 */
export function filterRevisions(revisions: DemoContractRevision[], tab: ReviewFilterTab): DemoContractRevision[] {
  if (tab.revIds.length === 0) return revisions
  return revisions.filter((r) => tab.revIds.includes(r.id))
}

/** 双语视图里的一行：一句英文 + 对应中文，两侧段数由修订切段决定 */
export interface AlignedRow {
  /** 全局唯一（条款号 + 句序） */
  key: string
  no: string
  titleEn: string
  titleZh: string
  /** 句中第一个未采纳修订的 id（用来看是否走查过） */
  rev?: string
  en: DemoNl2Clause['sentences'][number]['en']
  zh: DemoNl2Clause['sentences'][number]['zh']
}

/**
 * 把条款摊平成「每句一行」的对齐序列。
 *
 * 对齐要求两侧同段数：修订句左右各切 3 段（前缀 / 绿增 / 后缀），
 * 台账没写全的（只剩 2 段或 1 段）按空白补齐，避免右栏比左栏矮半行。
 */
export function alignClauses(clauses: DemoNl2Clause[]): AlignedRow[] {
  const rows: AlignedRow[] = []
  for (const c of clauses) {
    c.sentences.forEach((s, i) => {
      const rev = s.en.find((seg) => seg.rev)?.rev
      const pad = Math.max(s.en.length, s.zh.length)
      const en = [...s.en]
      const zh = [...s.zh]
      for (let k = en.length; k < pad; k++) en.push({ text: '' })
      for (let k = zh.length; k < pad; k++) zh.push({ text: '' })
      rows.push({ key: `${c.no}-${i}`, no: c.no, titleEn: c.titleEn, titleZh: c.titleZh, rev, en, zh })
    })
  }
  return rows
}

/** 接通的修订 id 集合（提交给法官/客户看的「已处理」口径） */
export function acceptedRevIds(decided: Record<string, 'accept' | 'reject'>): string[] {
  return Object.entries(decided)
    .filter(([, v]) => v === 'accept')
    .map(([k]) => k)
}

export interface WalkStats {
  accepted: number
  rejected: number
  done: boolean
}

/** 逐条采纳的进度：走到最后一条即 done */
export function walkStats(
  revisions: DemoContractRevision[],
  decided: Record<string, 'accept' | 'reject'>,
): WalkStats {
  const accepted = revisions.filter((r) => decided[r.id] === 'accept').length
  const rejected = revisions.filter((r) => decided[r.id] === 'reject').length
  return { accepted, rejected, done: accepted + rejected >= revisions.length }
}

/** 下一步要问的修订（全部处理完返回 null） */
export function nextRevision(
  revisions: DemoContractRevision[],
  decided: Record<string, 'accept' | 'reject'>,
): DemoContractRevision | null {
  return revisions.find((r) => !decided[r.id]) ?? null
}
