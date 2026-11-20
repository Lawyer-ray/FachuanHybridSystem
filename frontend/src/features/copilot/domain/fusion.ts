/**
 * 评审（Review）→ 多答裁决卡的视图映射。
 *
 * 输入是 snake_case 的**线上契约**（`adjudication-types.ts`，冻结），输出是
 * camelCase 的视图形状：组件只认这一层，不在 JSX 里读 `criteria_met` 这类线上
 * 字段——线上改名时读出来只会是 `undefined`，`tsc` 全绿、页面空白。
 *
 * 三条硬语义（都是"错了不报错、只会看起来正常"的那类）：
 *
 * 1. `score === null` = 一条有效票都没有，**不是 0 分**：原样保留 `null`，由视图
 *    显示「无有效判定」。写成 0 等于把"判不了"说成"全错"。
 * 2. `criteria_met === null` = judge 判不了（超时/解析失败/协议偏离），**不是**
 *    "不通过"：保留 `null` 并带上原因，不进"通过/不通过"的任何一边。
 * 3. `tie === true` = 没有可判定的代表：此时所有簇都**不突出**（不排序、不给推荐
 *    标记）。这是契约语义而不是样式偏好，`emphasized` 是给消费方读的那一位。
 *
 * `Review` 是判定快照，不可变；采纳记录走独立端点，见 `domain/adoption.ts`。
 */

import type { CriteriaVerdict, EquivalenceCluster, LaneReview, Review, ReviewStage, UnscoredReason } from '../adjudication-types'
import { agentLabel } from './dual'

/** 一栏的视图（`score === null` 表示无有效判定，**不是** 0） */
export interface LaneView {
  lane: string
  /** 栏头显示名（`agentLabel` 同口径；未知 kind 原样显示） */
  label: string
  valid: number
  yes: number
  score: number | null
  oneLine: string
}

/** 一条 rubric 对一栏的判定视图（`met === null` 表示 judge 判不了） */
export interface VerdictView {
  rubricId: string
  lane: string
  met: boolean | null
  explanation: string
  /** 支撑该判定的原文片段（点开分数看证据的数据源） */
  evidenceQuote: string
  judgeModel: string
  attempts: number
  /** 人读的"判不了"原因；有判定时为空串。未知原因降级为原字符串 */
  unscoredReason: string
}

/** 分歧点的一侧：这一栏对同一条 rubric 的立场与原文 */
export interface ConflictSideView {
  lane: string
  label: string
  met: boolean
  evidenceQuote: string
}

/** 同一条 rubric 上各栏判定相反（一方成立、一方不成立） */
export interface ConflictPairView {
  rubricId: string
  /** 各栏的非空判定（判不了不算立场，不进 sides） */
  sides: ConflictSideView[]
}

export interface ReviewView {
  reviewId: string
  stage: ReviewStage
  /** 一句话导航（后端 headline），不是法律结论 */
  headline: string
  lanes: LaneView[]
  verdicts: VerdictView[]
  conflicts: ConflictPairView[]
}

/**
 * 等价簇的视图。`emphasized` 是**唯一**允许消费方拿去做视觉突出的位：
 * `tie === true` 时全为 `false`，且不提供"排序后的第一条"这种东西。
 */
export interface ClusterView {
  memberIds: string[]
  representativeId: string
  tie: boolean
  emphasized: boolean
}

/** 判定"没结论"的原因闭集 → 人读文案；新增原因未收录时原样透出 */
const UNSCORED_LABELS: Record<UnscoredReason, string> = {
  parse_failed: '判定解析失败',
  protocol_deviation: '未按评分协议作答',
  timeout: 'judge 超时',
  judge_error: 'judge 调用失败',
  empty_response: 'judge 返回空正文',
}

/**
 * `unscored_reason` → 人读原因。
 *
 * 后端将来新增原因时这里会落到 `?? reason`：显示原始编码，不崩、不吞、不猜。
 */
export function unscoredLabelOf(reason: string): string {
  return UNSCORED_LABELS[reason as UnscoredReason] ?? reason
}

function toLaneView(lane: LaneReview): LaneView {
  return {
    lane: lane.lane,
    label: agentLabel(lane.lane),
    valid: lane.valid,
    yes: lane.yes,
    // null 原样保留：0 分与"无有效判定"是两件事
    score: lane.score,
    oneLine: lane.one_line,
  }
}

function toVerdictView(verdict: CriteriaVerdict): VerdictView {
  return {
    rubricId: verdict.rubric_id,
    lane: verdict.lane,
    met: verdict.criteria_met,
    explanation: verdict.explanation,
    evidenceQuote: verdict.evidence_quote,
    judgeModel: verdict.judge_model,
    attempts: verdict.attempts,
    // 只有"判不了"才有原因；有判定时即使线上留了脏值也不展示
    unscoredReason: verdict.criteria_met === null ? unscoredLabelOf(verdict.unscored_reason) : '',
  }
}

/**
 * 分歧点：同一条 rubric 上既有"成立"也有"不成立"。
 *
 * 判不了（`criteria_met === null`）不算立场——它没有说哪边对，拿它当一方会把
 * "judge 没答上来"渲染成"两家意见相反"。分组的出现顺序按 verdict 的到达顺序。
 */
export function conflictPairsOf(verdicts: readonly CriteriaVerdict[]): ConflictPairView[] {
  const byRubric = new Map<string, CriteriaVerdict[]>()
  for (const verdict of verdicts) {
    if (verdict.criteria_met === null) continue
    const list = byRubric.get(verdict.rubric_id)
    if (list) list.push(verdict)
    else byRubric.set(verdict.rubric_id, [verdict])
  }

  const pairs: ConflictPairView[] = []
  for (const [rubricId, list] of byRubric) {
    const hasMet = list.some((verdict) => verdict.criteria_met === true)
    const hasUnmet = list.some((verdict) => verdict.criteria_met === false)
    if (!hasMet || !hasUnmet) continue
    pairs.push({
      rubricId,
      sides: list.map((verdict) => ({
        lane: verdict.lane,
        label: agentLabel(verdict.lane),
        met: verdict.criteria_met === true,
        evidenceQuote: verdict.evidence_quote,
      })),
    })
  }
  return pairs
}

/** 线上 `Review` → 裁决卡视图。栏序/条目序一律按后端到达顺序，不排序 */
export function toReviewView(review: Review): ReviewView {
  return {
    reviewId: review.review_id,
    stage: review.stage,
    headline: review.headline,
    lanes: review.lanes.map(toLaneView),
    verdicts: review.verdicts.map(toVerdictView),
    conflicts: conflictPairsOf(review.verdicts),
  }
}

/**
 * 等价簇 → 视图。**`tie` 时不许突出任何一簇**：
 *
 * - 任一簇 `tie === true`（后端保证此时所有簇都是 tie）→ 所有 `emphasized=false`，
 *   且 `representativeId` 置空——消费方即使想"取第一条代表"也拿不到目标；
 * - 顺序原样保留，**不做**"按簇大小排序"：所谓推荐排序正是 tie 语义要禁止的东西。
 */
export function toClusterViews(clusters: readonly EquivalenceCluster[]): ClusterView[] {
  const tied = clusters.some((cluster) => cluster.tie)
  return clusters.map((cluster) => ({
    memberIds: [...cluster.member_ids],
    representativeId: tied ? '' : cluster.representative_id,
    tie: cluster.tie,
    emphasized: !tied && !cluster.tie,
  }))
}

/**
 * 评审卡该挂在哪一轮：后端的 `turn` = 会话里第几条 user 消息（1 起）。
 *
 * `messages` 是转录（结构上只要 `id`/`role`，便于纯测）。**窗口不完整时必须
 * 返回 null**：历史按 200 条分页，>200 条的老会话加载的是「最新一页」，从窗口
 * 里数 user 消息会少数几轮，把 A 轮的评审挂到 B 轮的答案下面——错位的证据比
 * 不显示更糟。`windowComplete` 由调用方按「已翻到顶 或 总量不足一页」判定。
 */
export function reviewTurnOf(
  messages: readonly { id: string; role: string }[],
  firstMessageId: string,
  windowComplete: boolean,
): number | null {
  if (!windowComplete) return null
  let turn = 0
  for (const message of messages) {
    if (message.role === 'user') turn += 1
    if (message.id === firstMessageId) return turn
  }
  return null
}
