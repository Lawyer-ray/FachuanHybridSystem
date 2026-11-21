/**
 * 泰国法核验 · 真接口调用
 *
 * ═══ 为什么要真调 ═══
 * 这一页此前是纯演示数据：点「核验法条」跑的是写死的四步日志，条文原文也是
 * 写死的字符串。录屏时如果观众问「这是真的查到的吗」，答不上来。
 *
 * 现在改成调后端 `/api/v1/legal-research/foreign-law/verify`，它背后是真
 * MCP 工具 `asean_law_verify` → 真 BARLC 数据库。返回的是真实条文原文。
 *
 * ═══ 接口形态（实测） ═══
 *   POST /api/v1/legal-research/foreign-law/verify
 *   { law_name: '民商法典', section_number: '538', country_code: 'LAWCOUNTRYTG', claim?: string }
 *   → { ok, verdict, law_title, section_number, section_text, reason,
 *       adjudicated, unconfirmed, needs_human, review_reasons, agreement,
 *       matched_by, elements, votes, jury_tokens }
 *
 * 两个坑（已踩）：
 *   · country_code 必须是 LAWCOUNTRYTG，不是 TH —— 传 TH 会 422
 *   · law_name 用「民商法典」，不是「泰国民商法典」—— 带国名前缀查不到
 *
 * 接口耗时 6–8 秒（BARLC 是境外站点），所以按钮点了要有明确等待态，
 * 不能让律师以为卡死了。
 */

import { createApiClient } from '@/lib/api'

const foreignLawApi = createApiClient({ prefix: '/api/v1/legal-research/foreign-law' })

/** 调用轨迹的一步（接入 → 登录 → 检索 → 取正文 → 切条款 → 取原文） */
export interface ForeignLawTraceStep {
  name: string
  detail: string
  ok: boolean
  result: string
  ms: number
}

/** 逐要件判定（律师问「哪一项没依据」时看的这一行） */
export interface ForeignLawElement {
  statement: string
  /** 支持 / 矛盾 / 原文未提及 */
  verdict: string
  reason?: string
}

/** 一个判定器的摘要（不含自由文本，后端刻意只透判定面） */
export interface ForeignLawVote {
  model: string
  /** balanced（中立）/ adversarial（对抗） */
  role: string
  verdict: string
  unscored_reason?: string
  /** 判定器回带的原文片段是否真的在条文里；null = 没提供 */
  evidence_ok?: boolean | null
  attempts?: number
  total_tokens?: number
}

/** 核验结果（后端原样返回） */
export interface ForeignLawVerifyResult {
  ok: boolean
  verdict?: string
  law_title?: string
  section_number?: string
  section_text?: string
  reason?: string
  /**
   * 合议**跑过**了（含「跑过但弃权」）。
   *
   * 与 `needs_model_judgement` 分工：合议跑过就没有「等别的模型判」这回事，
   * 弃权也是结论——所以不能根据 verdict 为空就提示律师「待判断」。
   */
  adjudicated?: boolean
  /** 没有结论（既不是支持/矛盾/未提及，也不是不存在该引用） */
  unconfirmed?: boolean
  /** 结论可用，但必须把 review_reasons 给律师看 */
  needs_human?: boolean
  review_reasons?: string[]
  /** 最高票 / 有效票；无有效票时 null（不是 0 分） */
  agreement?: number | null
  /** 怎么定位到这部法的：exact / containment / ambiguous */
  matched_by?: string
  elements?: ForeignLawElement[]
  votes?: ForeignLawVote[]
  jury_tokens?: number
  /** 合议结果来自缓存（此时 jury_tokens 是上次的成本） */
  cached?: boolean
  // ---- 溯源与生效版本 ----
  /** BARLC 详情页，给律师点回原页 */
  source_url?: string
  effective_date?: string
  revise_date?: string
  /** 时效告警。非空时必须原样展示 */
  version_warnings?: string[]
  /** @deprecated 判定已在插件里做完，只在合议关闭时才为 true */
  needs_model_judgement?: boolean
  claim?: string
  detail?: string
  /** 总耗时（毫秒） */
  total_ms?: number
  /** 调用轨迹：看得出系统真的连了 BARLC */
  trace?: ForeignLawTraceStep[]
}

/** 一处在合同里出现的泰国法引用 */
export interface ThaiLawCitation {
  /** 合同里的第几条 */
  article: string
  /** 引用的是哪部法 */
  lawName: string
  /** 第几条 */
  section: string
  /** 合同基于该条文得出的主张 */
  claim: string
}

/**
 * 演示用的引用清单。
 *
 * 刻意只留 3 条真实存在、能查到的：《泰国民商法典》第 538 / 546 / 549 条。
 * 数量少是为了演示时每条都能等它跑完（一条 6–8 秒，三条约 20 秒），
 * 而不是堆一堆走马观花。
 */
export const DEMO_THAI_CITATIONS: ThaiLawCitation[] = [
  {
    article: '第三条 租金',
    lawName: '民商法典',
    section: '538',
    claim: '租赁双方可约定租金调增，但单方将 CPI 全额转嫁缺乏对价平衡',
  },
  {
    article: '第四条 押金',
    lawName: '民商法典',
    section: '546',
    claim: '租赁期满后押金应予返还，仅在承租方实际欠付款项范围内可扣减',
  },
  {
    article: '第六条 提前解约',
    lawName: '民商法典',
    section: '549',
    claim: '提前解约的违约责任应与出租方实际损失相当',
  },
]

/** BARLC 的国家代码（不是 ISO 的 TH） */
export const BARLC_THAILAND = 'LAWCOUNTRYTG'

/** 核验一条引用 */
export async function verifyThaiLaw(c: ThaiLawCitation): Promise<ForeignLawVerifyResult> {
  return foreignLawApi
    .post('verify', {
      json: {
        law_name: c.lawName,
        section_number: c.section,
        claim: c.claim,
        country_code: BARLC_THAILAND,
      },
      // 接口实测 6–8 秒，给足 30 秒余量
      timeout: 30_000,
    })
    .json<ForeignLawVerifyResult>()
}
