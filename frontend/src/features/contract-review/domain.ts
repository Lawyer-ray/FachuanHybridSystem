/**
 * 复审工作台的纯逻辑：分组、统计、文件名规则。
 *
 * 与 UI 解耦的原因：这些规则要在测试里独立验证（排序稳定性、采纳后沉底、
 * 修订版命名），混在组件里只能靠 DOM 断言，脆且慢。
 */
import type { ReviewRevision, RevisionSeverity } from './types'

/** 严重度排序权重：高风险在前 */
const SEV_WEIGHT: Record<string, number> = { high: 0, medium: 1, low: 2, '': 3 }

/** 左栏分区：待决策在上、已处理沉底 */
export interface RevisionBuckets {
  pending: ReviewRevision[]
  decided: ReviewRevision[]
}

/**
 * 拆成「待决策 / 已处理」两桶。
 *
 * 桶内顺序：待决策按「严重度 → 原顺序」，让律师先看高危；已处理按原顺序，
 * 因为处理顺序本身就是他的工作轨迹，重排反而找不到刚才那条。
 */
export function bucketRevisions(items: ReviewRevision[]): RevisionBuckets {
  const pending = items
    .filter((r) => r.status === 'pending')
    .slice()
    .sort((a, b) => {
      const d = (SEV_WEIGHT[a.severity] ?? 3) - (SEV_WEIGHT[b.severity] ?? 3)
      return d !== 0 ? d : a.ordinal - b.ordinal
    })
  const decided = items
    .filter((r) => r.status !== 'pending')
    .slice()
    .sort((a, b) => a.ordinal - b.ordinal)
  return { pending, decided }
}

/** 严重度计数（只数待决策的，已处理的不再进风险统计） */
export function countBySeverity(items: ReviewRevision[]): Record<string, number> {
  const out: Record<string, number> = { high: 0, medium: 0, low: 0 }
  for (const r of items) {
    if (r.status !== 'pending') continue
    if (r.severity && r.severity in out) out[r.severity] = (out[r.severity] ?? 0) + 1
  }
  return out
}

/** 等级 → 中文标签（低等级或无等级返回空串，UI 不渲染徽章） */
export function severityLabel(sev: RevisionSeverity): string {
  if (sev === 'high') return '高'
  if (sev === 'medium') return '中'
  if (sev === 'low') return '低'
  return ''
}

/**
 * 定稿文件名：`原名.docx` → `原名[修订版]V1_20261024.docx`
 *
 * 对齐律师磁盘上的真实命名规律（见 prototype 的 roleOf/revisedName）：
 * 已有 `[whatever]` 后缀的先剥掉，避免出现 `[修订版]V1[修订版]V1`。
 */
export function revisedFileName(original: string, version = 1, date = new Date()): string {
  const base = original
    .replace(/\.docx$/i, '')
    .replace(/\[[^\]]*\](?:V\d+)?_?\d*$/, '')
    .trim()
  const stamp =
    String(date.getFullYear()) +
    String(date.getMonth() + 1).padStart(2, '0') +
    String(date.getDate()).padStart(2, '0')
  return `${base}[修订版]V${version}_${stamp}.docx`
}

/** 决策进度文案：「已处理 3 / 共 8」 */
export function progressText(total: number, pending: number): string {
  return `已处理 ${total - pending} / 共 ${total}`
}

/** 立场方的键（与后端 represented_party 对齐） */
export type PartyKey = 'party_a' | 'party_b' | 'party_c' | 'party_d'

/** 方位标签：甲乙丙丁 */
export function partyLabel(key: PartyKey): string {
  return { party_a: '甲方', party_b: '乙方', party_c: '丙方', party_d: '丁方' }[key]
}

/**
 * 从识别出的当事人里推荐「我方是哪一方」。
 *
 * **为什么不写死甲方**：合同可能有甲乙丙丁四方，我方也可能是乙方甚至丙方
 * （常见「代表客户股东去审」「我方是承租方/供应方」）。写死甲方会让整批
 * 建议方向反掉——同一份合同站甲方还是乙方，付款、违约、验收的改法完全相反。
 *
 * 匹配策略：委托客户名与某一方做「包含」双向比较（合同里常写全称、系统里
 * 存简称，或反过来）。匹配不上返回 `null`，由律师自己选——**宁可让他多点
 * 一次，也不要猜错方向**。
 */
export function recommendParty(
  parties: Record<string, string>,
  clientName?: string,
): PartyKey | null {
  const keys: PartyKey[] = ['party_a', 'party_b', 'party_c', 'party_d']
  const present = keys.filter((k) => (parties[k] ?? '').trim() !== '')

  if (!clientName?.trim()) return null
  const target = normalizeName(clientName)
  if (!target) return null

  for (const k of present) {
    const name = normalizeName(parties[k] ?? '')
    if (!name) continue
    if (name === target || name.includes(target) || target.includes(name)) return k
  }
  return null
}

/** 归一化公司名：去空白与常见后缀，避免「有限公司」之类的差异导致匹配失败 */
function normalizeName(s: string): string {
  return (s || '')
    // 含全角空格（中文公司名里常见）：用转义写法，避免源码里出现不可见字符
    .replace(/\s|\u3000/g, '')
    .replace(/[（(].*?[)）]/g, '')
    .trim()
}
