/**
 * AI 操作历史（`AgentUiAction` 台账）的行 → 展示模型（纯函数，无 React、无 IO）。
 *
 * 这张面板存在的理由只有一个：让律师核对「AI 到底动过什么」。所以每行必须
 * 同时答清三件事：
 * - **哪个动作**：中文名只能从后端 manifest 的生成物取（`UI_TOOL_BY_NAME`）。
 *   台账里存的是机器名，另抄一份中文表就是第二份真源，后端改文案这里不会跟。
 * - **什么结局**：六态各有各的文案。尤其 `denied` 与 `expired` 不能都写成
 *   「失败」——前者是律师自己的决定（拒绝），后者是系统在回执窗口到期后的
 *   兜底，事后追责问的是两件不同的事。
 * - **核实过没有**：页面回 `ok` 只代表它自己这么报；`verified=false` 是
 *   「页面说成功、库里没变」，这是整张表最需要律师看见的一行。
 */

// 直连生成物而不是 `../ui-tools` 桶：桶 → registry → discover 的 eager
// `import.meta.glob`（以及 hooks → store）会被一个纯函数模块整个拖进来；
// `generated.ts` 是零依赖叶子，也是这份清单的单一来源。
import type { UiActionHistoryItem } from '../api-types'
import { UI_TOOL_BY_NAME } from '../ui-tools/generated'
import type { UiToolName } from '../ui-tools/generated'

/** 台账结局六态（与后端 `AgentUiAction.outcome` 同值）；认不出的值按 `unknown` 展示 */
export type UiActionHistoryOutcome = 'ok' | 'error' | 'denied' | 'aborted' | 'expired' | 'unknown'

const OUTCOME_LABELS: Record<UiActionHistoryOutcome, string> = {
  ok: '成功',
  error: '失败',
  denied: '你拒绝了',
  aborted: '已中止',
  expired: '超时未处理',
  unknown: '结果未知',
}

/** 徽标色调：文字始终在，颜色只是第二眼（不能只靠颜色区分六种结局） */
export type UiActionHistoryTone = 'ok' | 'error' | 'warn' | 'muted'

/**
 * `denied` 与 `aborted` 走 muted：它们是人主动叫停的，不是系统故障；
 * `expired` 走 warn——没有人处理、系统替你关了，需要律师回头看一眼。
 */
const OUTCOME_TONES: Record<UiActionHistoryOutcome, UiActionHistoryTone> = {
  ok: 'ok',
  error: 'error',
  denied: 'muted',
  aborted: 'muted',
  expired: 'warn',
  unknown: 'muted',
}

/** 线上结局值 → 六态；新后端加了取值时退回 `unknown`（诚实：这一行结果不明） */
export function outcomeOf(raw: string): UiActionHistoryOutcome {
  return Object.hasOwn(OUTCOME_LABELS, raw) ? (raw as UiActionHistoryOutcome) : 'unknown'
}

/** 动作中文名：生成物里没有这个名字时退回动作名原文（宁可难看也不空着） */
export function uiActionTitle(action: string): string {
  return Object.hasOwn(UI_TOOL_BY_NAME, action) ? UI_TOOL_BY_NAME[action as UiToolName].title : action
}

export type UiActionVerifyKind = 'verified' | 'mismatch' | 'unverified'

/** 一行台账的核实状态（`null` = 这一行不显示核实，见 {@link verifyOf}） */
export interface UiActionHistoryVerifyView {
  kind: UiActionVerifyKind
  label: string
}

/**
 * 三态核实的展示口径：
 * - `true` → 服务端已核实；
 * - `false` → 页面报成功但库里没变（最重要的一种，渲染层据此标红）；
 * - `null` + `outcome=ok` → 未核实（核实器没跑或给不出结论）；
 * - 其余（没执行到 / 结局本来就不是 ok）不显示——没有「核实」可谈。
 */
function verifyOf(item: UiActionHistoryItem, outcome: UiActionHistoryOutcome): UiActionHistoryVerifyView | null {
  if (item.verified === true) return { kind: 'verified', label: '服务端已核实' }
  if (item.verified === false) return { kind: 'mismatch', label: '页面报成功但库里没变' }
  if (outcome === 'ok') return { kind: 'unverified', label: '未核实' }
  return null
}

const TIME_FORMAT = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

/** ISO 时刻 → 本地时区 `MM/DD HH:mm`；空串/坏值返回空串（调用方据此不渲染） */
export function formatHistoryTime(iso: string): string {
  if (!iso) return ''
  const at = new Date(iso)
  return Number.isNaN(at.getTime()) ? '' : TIME_FORMAT.format(at)
}

/** 一行台账的展示模型 */
export interface UiActionHistoryRow {
  /** 动作中文名（生成物里取不到时 = 动作名原文） */
  title: string
  action: string
  outcome: UiActionHistoryOutcome
  outcomeLabel: string
  outcomeTone: UiActionHistoryTone
  /** null = 这一行不显示核实状态（见 {@link verifyOf}） */
  verify: UiActionHistoryVerifyView | null
  /** 本地时区 `MM/DD HH:mm`；空串 = 时间不可读（不渲染） */
  at: string
  /** 原始 ISO：`<time dateTime>` 与列表 key 用 */
  createdAt: string
  /** 有批准人时的「经 X 批准」，否则空串 */
  approvedByLabel: string
}

export function toUiActionHistoryRow(item: UiActionHistoryItem): UiActionHistoryRow {
  const outcome = outcomeOf(item.outcome)
  return {
    title: uiActionTitle(item.action),
    action: item.action,
    outcome,
    outcomeLabel: OUTCOME_LABELS[outcome],
    outcomeTone: OUTCOME_TONES[outcome],
    verify: verifyOf(item, outcome),
    at: formatHistoryTime(item.created_at),
    createdAt: item.created_at,
    approvedByLabel: item.approved_by_name ? `经 ${item.approved_by_name} 批准` : '',
  }
}
