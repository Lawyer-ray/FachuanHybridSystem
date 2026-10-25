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
