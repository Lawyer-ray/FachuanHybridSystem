/**
 * 段级复核信号：`review_flag` → 人话（标签 + 为什么被标出来）。
 *
 * 与页级质量 / 跨页不一致都不相干：那两者说的是「识别结果哪里可疑」，这里说的是
 * 「这一段的分段边界可不可信」。同一句话要出现在段头徽标、左栏 tooltip、右栏提示条
 * 三处，所以只在这里拼一次，组件只做展示。
 */

/** 一段的复核信号归一后的形状（供段头徽标 / 左栏 tooltip / 右栏提示条共用） */
export interface SegmentReviewHint {
  /** 短标签：「建议复核」/「未识别」/「OCR 失败」 */
  label: string
  /** 为什么被标出来。拿不到具体原因时给空串——**不编原因**比编一条更可信 */
  reason: string
}

/** 后端 `PdfSplitReviewFlag` 的本地兜底文案（API 带了 `review_flag_label` 时优先用它） */
const REVIEW_LABELS: Record<string, string> = {
  low_confidence: '建议复核',
  unrecognized: '未识别',
  ocr_failed: 'OCR 失败',
}

/**
 * 分段来源 → 「为什么这一段让人不放心」（**只管规则引擎那几种结构成因**）。
 *
 * 取值来自后端 `segment_detector`：`layout_title` / `rule_weak_only` /
 * `rule_adjacent_start` / `rule_merged_adjacent` / `gap_fill`。
 * 模型侧（`llm*`）不在这里：同样是 llm，来源是「置信度低」还是「边界二审没过」
 * 结论完全相反，必须结合置信度判断，见 `reviewHintOf`。
 */
function structuralReasonOf(method: string | undefined): string {
  switch (method) {
    case 'layout_title':
      return '起点是按版面标题推断的，可能把上一份的末尾切进来'
    case 'rule_weak_only':
      return '只命中了弱规则（标题像、版式不像）'
    case 'rule_adjacent_start':
      return '和上一段的起点只隔一页，可能切得太碎'
    case 'rule_merged_adjacent':
      return '和相邻段拼过再拆开，边界可能偏'
    case 'gap_fill':
      return '这段是补空得来的（前后都没有明确标题）'
    default:
      return ''
  }
}

/**
 * 后端判定「模型自己都不太确定」的阈值（`llm_segment_detector`: `confidence < 0.6`）。
 *
 * 前端必须用同一个数：置信度只有**在这个数以下**才是复核的原因。90% 还要求复核的，
 * 说明触发的是另一种信号（边界二审没结论 / 合并继承），此时把 90% 当理由写在提示里，
 * 律师看到的是一句自相矛盾的话（「建议复核 · 置信度 90%」）。
 */
const LOW_CONFIDENCE_BELOW = 0.6

/**
 * 是否需要复核、为什么。
 *
 * ## 为什么要在这一层算
 *
 * 同一句话要出现在三处：中栏段头徽标、左栏段行 tooltip、右栏正文面板顶部提示条。
 * 三处各拼一遍文案，迟早出现「徽标说 62%，提示条说 60%」这种自相矛盾——律师
 * 一旦发现两处对不上，就会连带不信第三处。所以只在这里拼，组件只做展示。
 *
 * ## 为什么 low_confidence 的原因要看 `sourceMethod`
 *
 * 「建议复核」本身不构成行动：律师要知道的是**核对什么**。低置信度有四五种成因
 * （版面标题猜的起点、只命中弱规则、和上一段只隔一页……），对应的核对动作完全不同。
 */
export function reviewHintOf(seg: {
  reviewFlag?: string
  confidence?: number
  sourceMethod?: string
  reviewFlagLabel?: string
}): SegmentReviewHint | null {
  const flag = seg.reviewFlag
  if (!flag || flag === 'normal') return null
  const label = seg.reviewFlagLabel || REVIEW_LABELS[flag] || flag

  if (flag === 'low_confidence') {
    const conf =
      typeof seg.confidence === 'number' && Number.isFinite(seg.confidence) ? seg.confidence : null
    const pct = conf === null ? '' : `自动分段置信度 ${Math.round(conf * 100)}%`
    const lowByConfidence = conf !== null && conf < LOW_CONFIDENCE_BELOW

    // ① 规则引擎的结构成因（起点按版面标题猜的 / 只命中弱规则 / 与上一段只隔一页…）
    const structural = structuralReasonOf(seg.sourceMethod)
    if (structural) {
      // 百分比只在它**支持**这个结论时才出现（< 0.6）；否则不拿一个高数字来衬托「建议复核」
      return { label, reason: [structural, lowByConfidence ? pct : ''].filter(Boolean).join(' · ') }
    }

    // ② 置信度低本身就是原因（模型自报 < 0.6）。
    //    「模型把握不大」只在分段确实出自模型时说：来源不明（更老的取值 / 规则引擎
    //    的未知分支）时只报数字，不替它认领成因。
    if (lowByConfidence) {
      const byModel = typeof seg.sourceMethod === 'string' && seg.sourceMethod.startsWith('llm')
      return { label, reason: [byModel ? '模型对这一段的边界把握不大' : '', pct].filter(Boolean).join(' · ') }
    }

    // ③ 置信度不低却仍要复核 → 触发的是**结构化信号**，不是文字识别：
    //    边界二审没跑出结论（超次数上限 / 调用失败 / 输出非法），或由相邻段合并而来。
    //    这两类都**刻意不动 LLM 自报的置信度**（无校准依据，见后端
    //    `mark_unverified_boundaries` 的注释），所以这里绝不能再把 90% 当理由印出来——
    //    律师看到的会是一句自相矛盾的话（「建议复核 · 置信度 90%」）。
    if (conf !== null) {
      return { label, reason: `文字识别置信度 ${Math.round(conf * 100)}%，要核对的是分段边界（二审没能给出结论）` }
    }

    // ④ 什么都不知道就不编
    return { label, reason: '' }
  }
  if (flag === 'unrecognized') return { label, reason: '这一段没认出是哪类材料，可能是模板里没有的新类型' }
  if (flag === 'ocr_failed') return { label, reason: '这一段的文字没有取出来，正文可能是空的' }
  // 后端将来新增的取值：原样展示标签，原因留空（不编）
  return { label, reason: '' }
}
