/**
 * 多答裁决的**跨 lane 契约**（本文件冻结，父会话独占；lane 只读）。
 *
 * 后端同源定义：`backend/apps/agent/services/adjudication/contracts.py` 与
 * `backend/apps/contract_review/services/write_contracts.py`——
 * **三处必须同一次提交内对齐**，改字段先改
 * `docs/04-计划/活跃/adjudication-agent-assignments.md` 附录 A。
 *
 * ## 为什么是 snake_case
 *
 * 这些是**线上格式**（wire shape），不是前端领域模型：后端 review 端点直接返回
 * pydantic 契约对象，字段名就是 `criteria_met` / `review_id`。仓库既有惯例一致
 * （`AgentHistoryMessage` 也是 `message_id` / `agent_kind`）。
 * 需要 camelCase 的领域形状时，由消费方写映射函数，**不要在这里改字面量**——
 * 改字面量等于前端的类型和后端的 JSON 悄悄对不上，`tsc` 还全绿。
 *
 * ## 只放类型，不放运行时
 *
 * 这一层被两条 lane（A5 栏头体检、A9 裁决卡）同时消费，一旦掺进常量或默认值，
 * 两条 lane 就会各自扩展它。
 */

/** 判定的三态：`null` = 判不了（解析失败/超时/协议偏离），**不是**不通过 */
export type CriteriaMet = boolean | null

/**
 * 判定"没结论"的原因闭集，与后端 `CRITERIA_UNSCORED_REASONS` 逐字对应。
 * `criteria_met === null` 时才有值。
 */
export type UnscoredReason = 'parse_failed' | 'protocol_deviation' | 'timeout' | 'judge_error' | 'empty_response'

/** 一条 rubric 对一栏的一次判定 */
export interface CriteriaVerdict {
  rubric_id: string
  lane: string
  criteria_met: CriteriaMet
  explanation: string
  /** 支撑该判定的原文片段（"点开分数看证据"的数据源） */
  evidence_quote: string
  judge_model: string
  /** 实际调用次数（含重试） */
  attempts: number
  unscored_reason: UnscoredReason | ''
}

/** 一栏的汇总；`score === null` 表示该栏一条有效票都没有（不是 0 分） */
export interface LaneReview {
  lane: string
  /** 有效票 = 通过 + 不通过（判不了与失败都不算） */
  valid: number
  yes: number
  score: number | null
  /** 一句理由（≤40 字） */
  one_line: string
}

export type ReviewStage = 'shadow'

/** 一轮多答的评审结果 */
export interface Review {
  review_id: string
  session_id: string
  turn: number
  /** 用了哪把尺子、哪一版；校准按它归因，缺了不能进 kappa 统计 */
  rubric_id: string
  rubric_version: string
  stage: ReviewStage
  lanes: LaneReview[]
  verdicts: CriteriaVerdict[]
  /** 一句话导航，不是法律结论 */
  headline: string
  /** 提到但没被检索/核验兜住的东西 */
  unverified: string[]
}

/** 融合的一条命中（RRF 只吃名次，不吃原始分） */
export interface FusedHit {
  /** 业务去重键：`law:…::article:…` / `case:…` / `file:…::page:…`（带种类前缀，防撞键） */
  key: string
  score: number
  hit_count: number
  best_rank: number
  lanes: string[]
}

/**
 * "这几份答案其实是同一个立场"。
 *
 * `tie === true` = 没有可判定的代表（全异或最大簇并列）。此后端保证
 * **所有**簇 `tie=true` 且 `representative_id=""` —— UI 必须并排显示各立场，
 * **禁止**回落成第一条冒充共识。
 */
export interface EquivalenceCluster {
  member_ids: string[]
  representative_id: string
  tie: boolean
}

/** 合同侧：一处候选改写的状态 */
export type WritePatchStatus = 'proposed' | 'conflict' | 'merged' | 'applied' | 'rejected'

/** 合同侧：冲突种类 —— 互斥 / 完全重复 / 三方都没改（漏改） */
export type PatchConflictKind = 'overlap_diff' | 'duplicate' | 'missing'

/** 合同侧：一处冲突（同一条款下的若干 patch） */
export interface PatchConflict {
  subpath: string
  clause_key: string | null
  kind: PatchConflictKind
  patch_ids: string[]
  /** 给律师看的一句话（"第 7.2 条有两种改法…"） */
  summary: string
}
