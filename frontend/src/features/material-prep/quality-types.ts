/**
 * 识别质量统计的类型（页级质量 / 证件缺字段 / 跨页不一致 / 分歧裁定的总账）。
 *
 * 从 types.ts 拆出：这几者描述的都是「机器这次读出来的东西可不可信」，
 * 与草稿本体（mats/segs/infos）是两个关注点；types.ts 已顶到规模硬红线。
 * 消费方仍从 `../types` 引（那里 re-export），不必知道拆到了哪。
 *
 * `JudgeState` 是后加的一项：它描述的不是「读到了什么」，而是「那一步**跑没跑**」——
 * 但同属「机器事实」，且与 `EngineDisagreement` 成对出现（分歧清单 + 这些分歧有没有被自动判过）。
 */

/**
 * 页级质量统计（`PdfSplitJobOut.summary.page_quality`）。
 *
 * 真实痛点：164 页卷宗里 p147 是宗地图、p148 是平面图，OCR 只出 6 个字和 47 个字。
 * 律师在正文里看到几行零散字符，根本不知道那是图纸——而图纸恰恰是抵押案件的关键证据。
 *
 * 后端把「正文不可信」的页分类给：图形页（图纸/印章/照片）、稀疏页（字太少）、
 * 空白页、取字失败页。前端消费图形 / 证件 / **取字失败**三类做提示，
 * 空白页不打扰律师（删页是另一条交互）。
 *
 * 全部字段按可选读取：旧任务的 summary 里没有这个键，缺了不能崩。
 */
export interface PageQuality {
  graphic_pages?: number[]
  sparse_pages?: number[]
  blank_pages?: number[]
  /**
   * **取字失败**的页号（后端 `summary.page_quality.ocr_failed_pages`，旧任务没有该键）。
   *
   * 与 `blank_pages` 必须分开：`blank` 是「原件本来就没字」（删页是另一条交互，不打扰律师），
   * `ocr_failed` 是「我们一个字都没读出来」。后者整页正文是空的、不会出现在 Markdown 里、
   * 任务也不会失败——**唯一的痕迹就是少了一页内容**，所以必须显式告警。
   *
   * 实证代价（2026-11-25 一份真实卷宗）：某一页整案的核心事实（标的金额 + 生效
   * 刑事判决编号）就是这样静默消失的。
   */
  ocr_failed_pages?: number[]
  /** 逐页说明，键是页号字符串（"147": "疑似图形页…"） */
  details?: Record<string, string>
  /**
   * 证件页标识：键是页号字符串（"23"），值是证件类型码（`id_card` / `household` /
   * `marriage` / `property_cert` / `license` / `income_proof`）。旧任务没有该键。
   *
   * 与 `graphic_pages` 的区别：「图纸看不出内容」是**没有**内容，
   * 「证件页关键字段未读出」是**该有的内容在那儿但没读出来**——
   * 姓名、身份证号、住址是律师必须抄进卷宗的东西，指着「这页是图纸」没用。
   */
  doc_hints?: Record<string, string>
  /**
   * 证件页未读出的字段（`summary.page_quality.doc_missing`，键=页号）。
   *
   * 只有 `doc_hints` 非空的页才出现在这里。`missing` 为空数组不代表「没问题」：
   * 它表示工程上认得出类型、预期字段也都命中，但整页内容可疑（如满是乱码），
   * 律师看一眼类型就该去核对原页。
   */
  doc_missing?: Record<string, DocMissing>
}

/** 一页证件材料的缺字段记录（`PageQuality.doc_missing` 的条目） */
export interface DocMissing {
  /** 证件类型码（与 `doc_hints` 同口径） */
  doc?: string
  /** 未读出的字段名（原样展示，不翻译）；空数组 = 字段都在但内容可疑 */
  missing?: string[]
}

/**
 * 跨页文字不一致（`PdfSplitJobOut.summary.inconsistencies`）。
 *
 * 真实痛点：同一枚章被识别 150+ 次，其中 5 次错成「测试乙」（应为「测试甲」）。
 * 逐页翻不可能发现，所以列成全局清单，按 confidence 把最可疑的排在最前。
 *
 * ⚠️ `canonical` / `variant` 的语义**随 kind 变**：只有 frequency 下 canonical 才是
 * 「统计上判定为正确的写法」；entity_cluster 下它只是簇里出现页数最多的**参照**，
 * 没有任何证据说明哪个对（同姓同名首字的兄弟姐妹完全可能落进同一簇）。
 * 所以文案必须按 kind 分支，见 `inconsistencyKindOf` 与 InconsistencyDrawer。
 */
export interface Inconsistency {
  /** 出现次数多的那个写法（frequency 下视为正确写法；entity_cluster 下只是参照） */
  canonical: string
  /** 出现次数少的那个写法（frequency 下疑似错字；其它 kind 下是待核对的另一种写法） */
  variant: string
  canonical_count: number
  variant_count: number
  /** 不一致出现的页号（绝对页号） */
  pages: number[]
  /** 置信度：high 排最前；后端可能给空串或其他等级，按 low 兜底排序。
   *  frequency 恒 high；entity_cluster / id_malformed 恒 medium（不触发自动改正文建议） */
  confidence: string
  /**
   * 判据种类（后端逐条透出）：`frequency` 频次悬殊 / `entity_cluster` 同角色姓名多写法聚类 /
   * `id_malformed` 证件号结构不合法配唯一合法候选。
   *
   * 可选：旧任务产物与旧草稿没有该键，**缺省按 frequency 处理**（`inconsistencyKindOf`）。
   * 按字符串而不是联合类型收：后端将来加判据时前端不该整块崩，未知值回退 frequency 文案。
   */
  kind?: string
}

/**
 * 分歧自动裁定「没生效」的原因码。
 *
 * 与后端 `disagreement_judge.GATE_*` 一一对应；`unknown` 是不认识的取值（后端将来加码时
 * 不丢信息、也不误报成某个已知原因）。`gate_off` 与 `missing_key` 对应**两个不同的配置项**，
 * 所以不能合并成一个 bool：前者要改 `OCR_JUDGE_ENABLED`，后者要填 `OCR_JUDGE_API_KEY`。
 */
export type JudgeGateReason = 'enabled' | 'gate_off' | 'missing_key' | 'not_requested' | 'unknown'

/**
 * 一次识别里分歧裁定的总账（收窄后）。
 *
 * `requested` 是**任务级**开关（用户勾了什么），`enabled` 是**有效值**（任务要求 ∧ 部署可用）；
 * 两者不同时才说明「你开了但没生效」，这正是渲染提示的唯一条件。
 */
export interface JudgeState {
  requested: boolean
  enabled: boolean
  reason: JudgeGateReason
  /** 送进打分器的分歧条数（被四道闸门挡掉的也算在内） */
  annotated: number
  /** 自动裁定的条数。判定**不删除任何分歧**，只加标记 */
  accepted: number
  /** 留在人工清单里的条数 */
  human: number
}

/** 一页的表格列数与邻页不同（`summary.table_geometry.column_anomalies` 的条目） */
export interface ColumnAnomaly {
  page_no: number
  prev_page_no: number
  cols: number
  prev_cols: number
}

/**
 * 页级「识别风险」信号（收窄后，`draft/page-anomaly.ts` 的 `readPageAnomaly` 产出）。
 *
 * 两件事的共同点：任务状态是成功的、正文也生成了，但机器读出来的东西**本身可疑**。
 * - `degenerate_pages`：云端把该页读成复读循环、正文被清空，改由本地 OCR 兜底；
 * - `column_anomalies`：该页表格列数与邻页不同（列数突变通常是表头被并/拆列）。
 *
 * 全部字段按可选读取：旧任务的 summary 里两个键都没有，缺了不能崩。
 */
export interface PageAnomaly {
  degenerate_pages?: number[]
  column_anomalies?: ColumnAnomaly[]
}

/**
 * 按**源**（`PageKey.mi`）存的页级风险。
 *
 * 为什么必须按源：一个材料包可以有多份 PDF，各有自己的识别任务，页号从 1 重新开始。
 * 存成 `PageAnomaly` 单值的话，后一份的结果会整键覆盖前一份（丢页），而且「某份的 P5
 * 退化」会显示到**任何**源的 P5 段上（给错页提示）——比不提示更糟。
 * 键是 `String(mi)`：JSON 对象的键只能是字符串，草稿要落库，所以这里直接按字符串定形。
 */
export type PageAnomalyByMi = Record<string, PageAnomaly>
