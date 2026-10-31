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
 * 列表行用到的字段投影。
 *
 * 为什么投影：CaseOut 带 parties/assignments/logs/case_numbers/chats/contacts
 * 等七八个关联数组，列表页一个都不用。直接吃整个 CaseOut 会让列表的渲染
 * 依赖永远不动的那几个字段之外的形状——后端一改 logs 结构，列表类型也跟着变，
 * 白白制造「无关改动」的编译错误。
 *
 * `contract_name` / `cause_of_action` / `target_amount` / `current_stage`
 * 在生成物里是 optional + nullable，这里统一成「可能没有」，逼调用点处理空值。
 */
export interface CaseRow {
  id: number
  name: string
  status: string
  current_stage?: string | null
  cause_of_action?: string | null
  target_amount?: string | null
  filing_number?: string | null
  contract_id?: number | null
  contract_name?: string | null
  group_key?: string | null
  group_name?: string | null
  start_date?: string | null
}

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
