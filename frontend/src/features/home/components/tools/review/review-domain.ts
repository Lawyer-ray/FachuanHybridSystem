import type { components } from '@/types/api-schema'

/**
 * 块级可信度复核的纯领域逻辑。
 *
 * 为什么单独一层：这里有一条极易做错的语义边界——`confidence === null` 表示
 * **未评估**（后端没有该能力，或判定模型未运行/失败），`confidence === 0` 表示
 * **评估过且几乎肯定认错**。两者在复核界面上必须区别对待：
 *   - null → 「未评估」，不该混进「需复核」清单把人吓一跳，也不能显示成 0 分；
 *   - 0    → 「高度可疑」，必须置顶。
 * 任何把 null 当 0 或当 falsy 的写法都会破坏这个区分，所以集中在这里并单测覆盖。
 */

/** 后端块类型（架构层词汇，见 backend normalize_block_type） */
export type BlockType = 'text' | 'title' | 'table' | 'image' | 'formula' | 'header' | 'footer' | 'unknown'

export type ParseBlock = components['schemas']['ParseMemoryBlockOut']
export type ParseCoverage = components['schemas']['ParseCoverageOut']

/** 复核筛选档位 */
export type ReviewFilter = 'all' | 'flagged' | 'scored' | 'unscored'

/**
 * 块的评估状态。刻意用三态而非布尔：
 * 「有没有被打分」和「分数好不好」是两件事，混成一个 boolean 就再也分不出
 * 「未评估」和「评估为高分」。
 */
export type BlockScoreState = 'unscored' | 'risky' | 'confident'

/** 低于此分视为需要人工看一眼。Jev 类模型的 AUROC 高但官方明说没有通用阈值，
 *  这里是业务侧的保守初值，接入真实判定层后应按实测标定替换。 */
export const REVIEW_THRESHOLD = 0.85

/** 分数状态判定（null 安全是全部意义所在） */
export function scoreState(block: ParseBlock): BlockScoreState {
  // 显式判 null/undefined：不能用 `!block.confidence`，那会把 0 也当成未评估
  if (block.confidence === null || block.confidence === undefined) return 'unscored'
  return block.confidence < REVIEW_THRESHOLD ? 'risky' : 'confident'
}

/**
 * 是否该出现在「需复核」清单里。
 * 只认两种来源：后端明确标记 needs_review，或分数低于阈值。
 * **未评估不算需复核**——否则后端一不支持打分，整页就全红，用户会直接无视这个功能。
 */
export function needsReview(block: ParseBlock): boolean {
  return block.needs_review || scoreState(block) === 'risky'
}

/** 页眉页脚页码不参与复核（与后端 is_body 同口径：这些块常整段重复且无信息量） */
export function isBodyBlock(block: ParseBlock): boolean {
  return block.type !== 'header' && block.type !== 'footer'
}

/** 按页分组（保持原顺序；无页码的归到 0 组并以 null 表示） */
export interface PageGroup {
  pageNo: number | null
  blocks: ParseBlock[]
}

export function groupByPage(blocks: ParseBlock[]): PageGroup[] {
  const order: (number | null)[] = []
  const map = new Map<number | null, ParseBlock[]>()
  for (const b of blocks) {
    const key = typeof b.page_no === 'number' ? b.page_no : null
    let bucket = map.get(key)
    if (!bucket) {
      bucket = []
      map.set(key, bucket)
      order.push(key)
    }
    bucket.push(b)
  }
  return order.map((pageNo) => ({ pageNo, blocks: map.get(pageNo) ?? [] }))
}

/** 复核统计（徽标/摘要用） */
export interface ReviewStats {
  total: number
  body: number
  flagged: number
  risky: number
  unscored: number
  confident: number
}

export function reviewStats(blocks: ParseBlock[]): ReviewStats {
  const stats: ReviewStats = { total: blocks.length, body: 0, flagged: 0, risky: 0, unscored: 0, confident: 0 }
  for (const b of blocks) {
    if (isBodyBlock(b)) stats.body++
    if (needsReview(b)) stats.flagged++
    const state = scoreState(b)
    if (state === 'risky') stats.risky++
    else if (state === 'unscored') stats.unscored++
    else stats.confident++
  }
  return stats
}

/** 按筛选档位过滤（保持原顺序） */
export function filterBlocks(blocks: ParseBlock[], filter: ReviewFilter): ParseBlock[] {
  if (filter === 'all') return blocks
  if (filter === 'flagged') return blocks.filter(needsReview)
  if (filter === 'scored') return blocks.filter((b) => scoreState(b) !== 'unscored')
  return blocks.filter((b) => scoreState(b) === 'unscored')
}

/**
 * 一句话概括这次解析的可信度状况（给摘要行用）。
 *
 * 措辞刻意区分「未评估」与「全部可信」：后端不支持打分时如果说「全部可信」，
 * 等于用沉默给出保证，比不给结论更危险。
 */
export function reviewHeadline(stats: ReviewStats): string {
  if (stats.total === 0) return '本次解析没有块级结构'
  if (stats.flagged > 0) return `${stats.flagged} 块待复核 / 共 ${stats.total} 块`
  if (stats.unscored === stats.total) return `${stats.total} 块均未评估（当前引擎不提供可信度）`
  if (stats.unscored > 0) return `已评估 ${stats.total - stats.unscored} 块，其余 ${stats.unscored} 块未评估`
  return `${stats.total} 块全部在阈值以上`
}

/** 分数展示文本：null 显示「—」而不是 0.00，避免把未评估误读成零分 */
export function formatConfidence(confidence: number | null | undefined): string {
  if (confidence === null || confidence === undefined) return '—'
  return confidence.toFixed(2)
}

/**
 * 能力位是否支持「外挂可信度」。
 * 前端只读不猜：后端没声明 has_blocks / has_bbox 时不要在 UI 上暗示"可以去裁图复核"。
 */
export function canAttachConfidence(coverage: ParseCoverage | null | undefined): boolean {
  return !!coverage?.has_blocks && !!coverage?.has_bbox
}
