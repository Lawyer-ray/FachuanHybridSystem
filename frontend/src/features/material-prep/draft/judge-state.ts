import type { JudgeGateReason, JudgeState } from '../types'

/**
 * 「分歧自动裁定」这次到底判了没有、没判是为什么。
 *
 * ## 为什么这件事必须有前端落点
 *
 * 后端 `summary.engine_disagreements_judge` 从 v27.25.4 起就是**固定形状**（单引擎任务
 * 也给 `{enabled:false, requested:false, reason:'not_requested', …}`），`service.py` 的
 * 注释把用途写得很直白：*「前端拿它与 enabled 对比才能说『你开了但没生效』」*。
 * 而在此之前，前端一个键都没读——结果是「开关勾着、分歧全进人工、界面一个字都不解释」，
 * 律师只能得出「这功能坏了」，实际可能只是这台环境没配 Key。
 *
 * ## 两个字段的语义（别再合并成一个 bool）
 *
 * - `requested`：**任务级**开关。用户在材料预处理里勾了什么（默认勾着）。
 * - `enabled`：**有效值** = requested ∧ 部署侧可用（总闸打开且配了 Key）。
 * - `reason`：没生效的原因码，让提示能精确到「去改哪一个配置项」。
 *
 * 本模块只做收窄与文案，不做任何判定——门禁是后端的，前端只负责把人话补上。
 */

const REASONS: readonly JudgeGateReason[] = ['enabled', 'gate_off', 'missing_key', 'not_requested', 'unknown']

function isReason(v: unknown): v is JudgeGateReason {
  return typeof v === 'string' && (REASONS as readonly string[]).includes(v)
}

/** 计数一律兜底成 0：缺字段不该让整条提示炸掉，也不该把「未知」显示成 NaN。 */
function count(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) && n > 0 ? n : 0
}

/**
 * 把后端 `summary.engine_disagreements_judge` 收窄成明确结构。
 *
 * @param raw 接口原值（不可信：旧任务没有这个键，未来可能加字段）
 * @returns 缺键 / 非对象时返回 `null`——**旧任务**就是这么来的，此时整条提示都不该出现
 *          （与引入本功能前的界面逐位一致）。注意空对象 `{}` 也算缺键：那是后端
 *          归一化前的残留形状，按「没有这件事」处理比编一个 `enabled:false` 更诚实。
 */
export function readJudgeState(raw: unknown): JudgeState | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  // 空对象 = 没有任何一项事实，等同缺键
  if (Object.keys(r).length === 0) return null
  const enabled = r.enabled === true
  return {
    requested: r.requested === true,
    enabled,
    // 原因码缺失时按 enabled 反推：能说「生效了」就不该说「未知」
    reason: isReason(r.reason) ? r.reason : enabled ? 'enabled' : 'unknown',
    annotated: count(r.annotated),
    accepted: count(r.accepted),
    human: count(r.human),
  }
}

/**
 * 多个 PDF 合成一份卷级判断。
 *
 * 一次识别可能提交多个 PDF，各任务带各自的判定总账。实践中它们由同一个部署门禁
 * 决定，结论必然一致；真不一致时**优先保留「要求了但没生效」那一条**——那是唯一
 * 需要律师知道（且能上报给管理员修）的事实，其余都只是「生效了/没要求」。
 */
export function mergeJudgeStates(states: (JudgeState | null | undefined)[]): JudgeState | null {
  const defined = states.filter((s): s is JudgeState => Boolean(s))
  if (defined.length === 0) return null
  const blocked = defined.find((s) => s.requested && !s.enabled)
  if (blocked) return blocked
  const judged = defined.find((s) => s.enabled && s.annotated > 0)
  return judged ?? defined[0]!
}

/** 原因码 → 一句**可执行**的话（常驻提示与收尾提示共用，避免两处口径分裂）。 */
export function judgeGateReasonText(reason: JudgeGateReason): string {
  switch (reason) {
    case 'missing_key':
      return '本环境未配置 OCR_JUDGE_API_KEY'
    case 'gate_off':
      return '本环境未开启打分器（系统配置 OCR_JUDGE_ENABLED=0）'
    default:
      // enabled 不该走到这里（调用方先判 enabled）；not_requested 同理。
      return '本环境未启用打分器'
  }
}

/**
 * 阅读器顶部的常驻提示：只在「用户要求了但没生效」时给一句话。
 *
 * 其余三种状态一律 `null`：
 * - 生效了 → 分歧清单自己会显示「已自动裁定」，不需要额外横幅；
 * - 用户自己关的（`requested=false`）→ 那是他的选择；
 * - 旧任务（`null`）→ 那时还没有这个功能。
 *
 * **不上彩色**：这是事实陈述，不是错误。染成黄色会让真正的失败提示（页级取字失败）
 * 贬值——与 `MetaPanel` 里质量提示条的分色口径一致。
 */
export function judgeGateNotice(state: JudgeState | null | undefined): string | null {
  if (!state || !state.requested || state.enabled) return null
  return `分歧自动裁定未生效：${judgeGateReasonText(state.reason)}。本卷分歧已全部进人工清单。`
}

/**
 * 收尾提示（toast）的尾句。
 *
 * 比常驻提示多说一件事：生效时的**结果**（裁定了几条、几条留人工）。没生效时的措辞
 * 收得比横幅短：toast 一行放不下「去改哪个配置项」的完整因果，那句话留给横幅。
 */
export function judgeOutcomeNote(state: JudgeState | null | undefined): string | null {
  if (!state || !state.requested) return null
  if (!state.enabled) return `分歧自动裁定未生效（${judgeGateReasonText(state.reason)}）`
  if (state.accepted > 0) return `已自动裁定 ${state.accepted} 条分歧，${state.human} 条待人工`
  if (state.annotated > 0) return `${state.annotated} 条分歧未能判定，已全部转入人工清单`
  return null
}
