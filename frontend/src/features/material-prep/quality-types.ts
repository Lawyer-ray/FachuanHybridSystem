/**
 * 识别质量统计的类型（页级质量 / 证件缺字段 / 跨页不一致）。
 *
 * 从 types.ts 拆出：这三者描述的都是「机器这次读出来的东西可不可信」，
 * 与草稿本体（mats/segs/infos）是两个关注点；types.ts 已顶到规模硬红线。
 * 消费方仍从 `../types` 引（那里 re-export），不必知道拆到了哪。
 */

/**
 * 页级质量统计（`PdfSplitJobOut.summary.page_quality`）。
 *
 * 真实痛点：164 页卷宗里 p147 是宗地图、p148 是平面图，OCR 只出 6 个字和 47 个字。
 * 律师在正文里看到几行零散字符，根本不知道那是图纸——而图纸恰恰是抵押案件的关键证据。
 *
 * 后端把三类「正文不可信」的页分开给：图形页（图纸/印章/照片）、稀疏页（字太少）、
 * 空白页。前端只消费前两类做提示，空白页不打扰律师（删页是另一条交互）。
 *
 * 全部字段按可选读取：旧任务的 summary 里没有这个键，缺了不能崩。
 */
export interface PageQuality {
  graphic_pages?: number[]
  sparse_pages?: number[]
  blank_pages?: number[]
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
