import type { components } from '@/types/api-schema'

/**
 * 本 feature 的类型出口。
 *
 * 原则：**能直接用生成物就用生成物**，只在生成物不够用时才手写投影。
 * 手写的地方必须写清「为什么生成物不够」——否则下一个接手的人会以为是漏生成。
 */

/** 案件（生成物原样） */
export type Case = components['schemas']['CaseOut']

/**
 * 列表行用到的字段投影（字段与可空性全部取自生成物 CaseOut）。
 *
 * 为什么投影：CaseOut 带 parties/assignments/logs/case_numbers/chats/contacts
 * 等七八个关联数组，列表页一个都不用。直接吃整个 CaseOut 会让列表的渲染
 * 依赖永远不动的那几个字段之外的形状——后端一改 logs 结构，列表类型也跟着变，
 * 白白制造「无关改动」的编译错误。
 *
 * 为什么不手写：手写版把 `id` 写成必填，还写了 CaseOut 里根本没有的
 * contract_name / group_key / group_name —— 调用点只好用 `as unknown as` 把差异盖住。
 * 现在一律 Pick 生成物：`id` 保持 `number | null` 口径，由列表页显式处理。
 */
/**
 * 列表行口径：后端 `slim=true` 的 `CaseSlimOut`。
 *
 * 标量列与 `CaseOut` 完全一致（后端同一份 CASE_SCALAR_FIELDS），差别只在
 * `CaseSlimOut` 不含那 7 个嵌套集合——所以下面的 Pick 在两边都成立，但指向
 * `CaseSlimOut` 才能让类型和后端实际返回的形状一致（否则谁往 CaseRow 里加
 * 一个集合字段，类型会静默放行、运行时拿到 undefined）。
 */
export type CaseRow = Pick<
  components['schemas']['CaseSlimOut'],
  'id' | 'name' | 'status' | 'current_stage' | 'cause_of_action' | 'target_amount' | 'filing_number'
>

/** 材料槽位状态：ok 齐备 / miss 缺件 / stale 待更新 / na 不适用 */
export type SlotStatus = 'ok' | 'miss' | 'stale' | 'na'

/** 进度条上的一档 */
export interface ReadinessCheck {
  key: string
  label: string
  ok: boolean
  detail: string
  field?: string
}

/** 一张网立案类型：民事一审 / 执行 */
export type FilingType = 'civil' | 'execution'

/** 立案引擎：走 HTTP 接口 / 走浏览器自动化 */
export type FilingEngine = 'api' | 'playwright'
