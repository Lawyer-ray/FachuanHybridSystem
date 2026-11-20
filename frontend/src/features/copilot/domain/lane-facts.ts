/**
 * 一栏回答的「体检事实」：消息本身能直接读出来的东西（引用 / 工具 / 截断 /
 * 失败），**只算事实、不打分**（纯函数，无 React、无 IO）。
 *
 * 存在理由：多答并排几份意见时，读起来最累的不是正文长短，而是三个问题要在三栏
 * 之间来回翻——「这一栏查过没有」「结论有没有来源」「是不是被截断了」。答案本来
 * 就在 `ChatMessage` 里（`citations` / `tools` / `truncated` / `failed`），本模块
 * 只把它们摊成一份可展示的事实表。
 *
 * **为什么不算分**：分数需要一个口径（引用几条算好、几个工具算够），任何口径都
 * 是产品判断，而这一层要被栏头（A5）与裁决卡（A9）共用。先钉死事实层，排序与
 * 打分留给上层（`LaneReview.score` 那类字段）。
 *
 * 口径约定（改之前先读 types.ts 对应字段的注释）：
 * - `citations` 缺失 = 本轮没有来源（旧数据 / 后端未接），按 0 条计——不编造，
 *   也不当成「引用丢失」；
 * - `tools` 只有多栏路径（`mergeAgentAnswers`）才填，所以「零工具」这条事实只在
 *   多栏栏头成立（本模块的调用点只有 `LaneFactsBadge`）；单栏 `tools` 恒为
 *   undefined，不可据此说「没查」；
 * - 「没有」只在**收尾且未被截断**时才是结论：流式中数据还在长，截断则是没跑完
 *   （引用/工具都可能还在路上），两种情况都不能写「无引 / 无工具」。
 */

import type { ChatMessage } from '../types'
import { shortToolName } from './reference'

/**
 * 核验类工具的短名闭集：只收「引用存在性 / 条款核查」这一类。
 *
 * 为什么是闭集而不是 `name.includes('check')` 这类模式：工具面有 400+ 个名字，
 * 模式匹配会把 `check_oa_credential`、`get_archive_checklist` 这些**与引用无关**
 * 的工具算成「已核验」——栏头就成了假阳性告知，比不显示糟得多。
 *
 * 三个名字与后端 `services/chat/citations.py` 的 TOOL_SPECS 法条核查两项、
 * 以及 `asean_law_verify`（域外法核验）逐名对齐；后端加核验工具时这里要同步。
 */
const VERIFICATION_TOOLS: ReadonlySet<string> = new Set([
  'verify_citations',
  'check_law_references',
  'asean_law_verify',
])

/** 一栏回答的体检事实（字段都是「消息里有什么」，没有评价性字段） */
export interface LaneFacts {
  /** 本轮入站引用条数（`citations` 缺失按 0） */
  citationCount: number
  /** 用过的核验类工具短名（去重，按首次调用顺序） */
  verificationTools: string[]
  /** 该栏调用过的工具条数（`tools` 由 mergeAgentAnswers 归位，多栏才有） */
  toolCount: number
  /** 回答被停止 / 断连截断（服务端 `metadata.truncated` 透传） */
  truncated: boolean
  /** 这一栏本轮没跑成（后端报错 / 配额降级） */
  failed: boolean
  /** 已回答完（不再流式）：只有收尾后「没有」才是事实 */
  settled: boolean
}

/**
 * 一条回答 → 体检事实。
 *
 * 工具名走 `shortToolName` 归一（与栏头工具 chip 同一个口径），否则
 * `mcp__fachuan__verify_citations` 会漏判；空名工具拿到的是「工具」占位，不在
 * 闭集内，自然不会误判成核验。
 */
export function laneFactsOf(message: ChatMessage): LaneFacts {
  const verificationTools: string[] = []
  for (const tool of message.tools ?? []) {
    const name = shortToolName(tool.toolName)
    if (VERIFICATION_TOOLS.has(name) && !verificationTools.includes(name)) {
      verificationTools.push(name)
    }
  }
  return {
    citationCount: message.citations?.length ?? 0,
    verificationTools,
    toolCount: message.tools?.length ?? 0,
    truncated: message.truncated === true,
    failed: message.failed === true,
    settled: message.streaming !== true,
  }
}

/**
 * 栏头徽标正文（一条紧凑的单行文字，细节走 {@link laneFactsDetail} 的 title）。
 *
 * 四条取舍，改之前先想清楚：
 * 1. **零数据整块不渲染**（返回空串）：一条既没引用、也没工具、又没截断/失败的
 *    回答，画一个「无引 · 无工具」的徽标等于栏头多一个看不懂的小方块，而且
 *    `citations` 缺失本来就分不清「没引」与「旧数据 / 后端未接」（见 types.ts）。
 * 2. **缺席只在有数据时才算事实**：查过工具却没引来源（`无引`）、有引用却没调
 *    任何工具（`无工具`），这两句才有信息量；都为空时什么都不说。
 * 3. **「没引 / 没查」要回答真的跑完才成立**：流式中的「还没有」不是事实，被
 *    截断的回答同理（引用和工具可能正在来的路上）——两处都走 `absenceIsFact`
 *    这一道关。
 * 4. **失败栏只说「未做」**：其余三项都是「没跑起来」的副产品，列出来像在给
 *    一个空栏打分。
 */
export function laneFactsBadge(facts: LaneFacts): string {
  if (facts.failed) return '未做'
  // 零数据：这一栏没有任何可报的事实（流式刚开始时也是这一档）
  if (!facts.truncated && facts.citationCount === 0 && facts.toolCount === 0) return ''
  // 「没有」只在回答完整跑完时才是结论（流式中 / 被截断 = 数还在路上）
  const absenceIsFact = facts.settled && !facts.truncated
  const parts: string[] = []
  if (facts.truncated) parts.push('截断')
  if (facts.citationCount > 0) parts.push(`引 ${facts.citationCount}`)
  else if (absenceIsFact) parts.push('无引')
  if (facts.verificationTools.length > 0) parts.push('核验')
  if (absenceIsFact && facts.toolCount === 0) parts.push('无工具')
  return parts.join(' · ')
}

/**
 * 悬停明细（`title`）：把徽标里的每个缩写还原成完整一句 + 数字（含 0）。
 *
 * 徽标正文受宽度限制只能写「引 3、核验」，明细里才说得清「引用 3 条、核验工具
 * verify_citations、工具 5 个」。流式中的数字是**还在长的**，必须写明，否则律师
 * 会把「引用 1 条」当成最终值。
 */
export function laneFactsDetail(facts: LaneFacts): string {
  // 失败栏的其余三项都是「没跑起来」的副产品，写出来只会像在给空栏打分
  if (facts.failed) return '本轮未做（该栏没跑成）'
  const parts = [
    facts.truncated ? '回答被截断（停止或断连，可能不完整）' : '',
    `引用 ${facts.citationCount} 条`,
    facts.verificationTools.length > 0
      ? `核验工具 ${facts.verificationTools.join(' / ')}`
      : '未用核验工具',
    `工具 ${facts.toolCount} 个`,
    facts.settled ? '' : '仍在流式，数字还在累计',
  ]
  return parts.filter(Boolean).join(' · ')
}
