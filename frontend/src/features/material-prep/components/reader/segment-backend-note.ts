/**
 * 「这段/这批结果到底是律所 AI 分的还是规则引擎兜的」——来源标记的读取、
 * 规则段计数、以及给律师看的那一句话。
 *
 * 从 `auto-split-helpers.ts` 拆出的原因：这是**对结果的可信度归因**，
 * 与「怎么轮询任务」（`poll-job.ts`）、「OCR 块怎么拼正文」（`ocr-blocks.ts`）
 * 是两个关注点。它一条 I/O 都没有、只吃后端返回的 summary / source_method，
 * 单独成文件后，改这套措辞与判定口径时不必碰到轮询循环。
 */

/**
 * 分段来源标记：summary 是自由字典，取不到就当规则引擎（保守，不谎报 AI 分段）。
 *
 * 后端三态：`llm` 全 LLM 批 / `mixed` 有规则降级批 / `rule` 全规则。
 * 原样透出给 `segmentBackendNote` 汇总，不在这里做语义判断。
 */
export function segmentBackendOf(job: { summary: Record<string, unknown> }): string {
  const backend = job.summary.segment_backend
  return typeof backend === 'string' ? backend : ''
}

/**
 * 段级来源是否属于「要律师重点复核的非 AI 分段」。
 *
 * 用**排除法**而不是只认 `'rule'`：规则引擎实际产出多种 source_method
 * （backend segment_detector.py：`rule` / `layout_title` / `rule_weak_only` /
 * `rule_adjacent_start` / `rule_merged_adjacent` / `gap_fill`），只认 `'rule'` 会少报，
 * 律师以为只有几段要复核。排除法对将来新增的规则变体天然生效，不会再漏。
 *
 * 排除两类：
 *  · `llm` 前缀 —— LLM 分段（后端自己也用 `startswith("llm")` 判，见 job_service.py:694）；
 *  · `manual` —— 人工确认/新建段（confirm 路径缺省即 manual，job_service.py:514）。
 *    把律师自己分的段说成「规则分段请重点复核」是倒打一耙。
 *
 * 空/缺失不判为规则（不能凭猜断言来源）。机械按页切分 `page_split` 会计入：
 * 它同样不是内容分析的结果，宁可多报也不漏报（本 feature 走 content_analysis，正常不出现）。
 */
function isReviewNeededMethod(raw: string | undefined): boolean {
  const method = (raw ?? '').trim()
  if (!method) return false
  return !method.startsWith('llm') && method !== 'manual'
}

/**
 * 一批结果里有几段是规则引擎兜的。
 *
 * 有段级 `source_method` 就**完全按它算**（哪怕算出 0）——它逐段落库，比 summary 准；
 * 一个标记都没有时才用 summary 兜底：明说全规则就按整批计，来源不明不猜成规则。
 */
export function ruleSegmentCountOf(backend: string, segments: { source_method?: string }[]): number {
  const marked = segments.filter((s) => (s.source_method ?? '').trim())
  if (marked.length > 0) return marked.filter((s) => isReviewNeededMethod(s.source_method)).length
  return backend === 'rule' ? segments.length : 0
}

/**
 * 分段来源 → 律师能据此决定要不要复核的一句话。
 *
 * `mixed`（部分批降级规则引擎）必须说出来：以前只认 llm/非 llm，mixed 会被算进
 * 「其余规则引擎」甚至「全规则」，把一次部分降级说成整份降级。规则分段的边界质量
 * 明显低于 LLM，所以带规则时把段数一并报出来，让律师知道要重点看几段。
 */
export function segmentBackendNote(backends: string[], ruleSegments: number): string {
  if (backends.length === 0) return ''
  // 整本一次（`llm_wholebook`）与整本+交叉（`llm_wholebook_cross`）都是 LLM 分段，
  // 而且比逐批看得更全。不认它们会被算进「其余含规则引擎」，把一次更好的分段说成降级。
  const wholebook = backends.filter((b) => b === 'llm_wholebook' || b === 'llm_wholebook_cross').length
  const llm = backends.filter((b) => b === 'llm').length
  const mixed = backends.filter((b) => b === 'mixed').length
  const cross = backends.filter((b) => b === 'llm_wholebook_cross').length
  const review = ruleSegments > 0 ? `；${ruleSegments} 段为规则分段请重点复核` : ''
  const crossNote = cross > 0 ? '；两种切法不一致的段已标「待裁定」' : ''
  if (wholebook > 0 && llm + wholebook === backends.length) {
    return `律所 AI 分段（整本一次${cross > 0 ? ' + 交叉核对' : ''}）${crossNote}`
  }
  if (llm + wholebook === backends.length) return '律所 AI 分段'
  if (llm === 0 && wholebook === 0 && mixed === 0) return `规则引擎分段（律所 AI 不可用）${review}`
  if (llm === 0 && wholebook === 0) return `律所 AI 与规则引擎混合分段${review}`
  return `${llm + wholebook}/${backends.length} 律所 AI 分段，其余含规则引擎${review}`
}
