import {
  getCase,
  getCaseFilingInfo,
  getMaterialStatus,
  getReadiness,
  listCases,
  type CaseFilingInfo,
  type MaterialStatus,
  type Readiness,
} from '../api'

import { useLoad } from './use-async-load'

/** 案件列表 */
export function useCases() {
  return useLoad(() => listCases(), [])
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
