import {
  getCase,
  getCaseFilingInfo,
  getMaterialStatus,
  getReadiness,
  listCases,
  type CaseFilingInfo,
  type CaseListSort,
  type MaterialStatus,
  type Readiness,
} from '../api'

import { useLoad } from './use-async-load'

/** 案件列表的查询口径：分页 / 搜索 / 排序全部下推后端（一页只有 pageSize 行，前端筛排没意义） */
export interface CasesQuery {
  /** 1 起的页码（内部换算成 offset） */
  page: number
  pageSize: number
  /** 关键词：命中 name 或 cause_of_action；空串 = 不过滤 */
  search?: string
  /** 排序口径（案件列表页要「待立案优先」→ 'filable_first'） */
  sort?: CaseListSort
}

/**
 * 案件列表（服务端分页）。
 *
 * 总数一并取（withTotal）：分页条要算总页数，而总数在响应头 X-Total-Count 里，
 * 只能由 api 层解析后随行一起交上来，页面拿不到 header。
 *
 * deps 用换算后的 offset 而不是 page：请求参数只由 (offset, limit, search, sort)
 * 这四个**原始值**决定，所以 params 对象每帧换新也不会多打一次请求。
 */
export function useCases({ page, pageSize, search, sort }: CasesQuery) {
  const offset = (page - 1) * pageSize
  return useLoad(
    () => listCases({ offset, limit: pageSize, search, sort, withTotal: true }),
    [offset, pageSize, search, sort],
  )
}

/** 单案详情 */
export function useCase(caseId: number | null) {
  return useLoad(
    () => (caseId ? getCase(caseId) : Promise.reject(new Error('未指定案件'))),
    [caseId],
  )
}

/** 材料齐备度 */
export function useMaterialStatus(caseId: number | null) {
  return useLoad<MaterialStatus>(
    () => (caseId ? getMaterialStatus(caseId) : Promise.reject(new Error('未指定案件'))),
    [caseId],
  )
}

/** 起诉 / 答辩条件 */
export function useReadiness(caseId: number | null) {
  return useLoad<Readiness>(
    () => (caseId ? getReadiness(caseId) : Promise.reject(new Error('未指定案件'))),
    [caseId],
  )
}

/** 一张网立案前置信息（有没有法院凭证、是不是原告方…） */
export function useCaseFilingInfo(caseId: number | null) {
  return useLoad<CaseFilingInfo>(
    () => (caseId ? getCaseFilingInfo(caseId) : Promise.reject(new Error('未指定案件'))),
    [caseId],
  )
}
