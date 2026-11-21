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
  /**
   * 各栏答案「其实是不是同一个立场」（双向蕴含成团）。
   *
   * 空列表有两种含义，**必须配合** {@link Review.clusters_error} 才能区分：
   * 错误为空 = 没跑成团（旧数据 / 单栏）；错误非空 = 跑了但失败。
   */
  clusters: EquivalenceCluster[]
  /**
   * 成团失败的原因（空串 = 成功或未跑）。
   *
   * **绝不许**把失败折算成「三份全异」：判等超时与「三份真的不一样」对律师是
   * 完全不同的信息（见 `toClusterViews` 的 tie 语义）。
   */
  clusters_error: string
}

/**
 * `dropped[].reason` 的封闭集，与后端 `contracts.DROPPED_REASONS` 逐字对应。
 *
 * - `empty` 该栏本轮没有正文；
 * - `failed` 该栏本轮失败（没有可聚合的回答）；
 * - `too_long` 单栏正文超过长度上限、被截后才进 prompt。
 *
 * 三者都不是「候选没参与」——它们必须被展示出来，否则聚合稿少了一栏的来源。
 */
export type DroppedReason = 'empty' | 'failed' | 'too_long'

/** 综合结论里的一条来源锚点：哪一栏、引了哪一句（只做锚点，不是核验结果） */
export interface SynthesisCitation {
  lane: string
  /** 从该栏原文抽出的引用串（法条名或案号），原样保留、不归一化 */
  quote: string
}

/** 没进聚合 prompt 的候选：栏 + 封闭原因（{@link DroppedReason}） */
export interface DroppedCandidate {
  lane: string
  reason: DroppedReason
}

/**
 * 一次「综合结论」的线上形状（`POST .../synthesize` 响应与 `GET .../synthesis` 回放同形）。
 *
 * 与 {@link Review} 的分工：`Review` 判「哪栏更好」（打分），`Synthesis` 产「一份合成稿」
 * （结论）。两者互不依赖，可以只跑其中一个。camelCase 的视图形状在
 * `domain/fusion.ts` 的 `SynthesisView`（本文件只放线上形状，见模块头）。
 */
export interface Synthesis {
  synthesis_id: string
  session_id: string
  turn: number
  /** 合成后的正文（Markdown）；空 = 没合成出东西，前端整卡不渲染 */
  text: string
  /** 实际执行合成的模型（不是候选模型） */
  model: string
  /** 真正进了 prompt 的栏（顺序 = 请求顺序） */
  lanes_used: string[]
  /** 没进 prompt 的栏及原因；与 `lanes_used` 互斥且并集 = 请求的栏 */
  dropped: DroppedCandidate[]
  /** 逐条来源锚点 */
  citations: SynthesisCitation[]
  /** 提到但检索/核验没兜住的引用（「没核上」不是「错」） */
  unverified: string[]
  /** 合成自身的 token 成本（与各栏生成成本分开记） */
  tokens: Record<string, number>
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
