import { useEffect, useState } from 'react'

import { errMessage } from '@/lib/errors'

import {
  getCase,
  getCaseFilingInfo,
  getMaterialStatus,
  getReadiness,
  listCases,
  listOAConfigs,
  runConflictCheck,
  type CaseFilingInfo,
  type ConflictCheck,
  type MaterialStatus,
  type OAConfig,
  type Readiness,
} from '../api'

/** 通用「一次性拉取」状态：loading / error / data 三态，够用且不引 react-query */
export interface AsyncState<T> {
  loading: boolean
  error: string | null
  data: T | null
}

const INIT = { loading: true, error: null, data: null } as const

/**
 * 拉一次数据。
 *
 * 为什么不用 react-query：本 feature 的读取全是「进页面拉一次、动作后手动刷新」，
 * 没有共享缓存与失效传播的需求（每个案件的数据只这一个页面看）。手写 effect
 * 反而让「什么时候重新拉」看得见——react-query 的 staleTime 猜错了会静默给旧数据，
 * 而立案状态这种数据给旧的是会出事的。
 */
function useLoad<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>(INIT)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fn()
      .then((d) => {
        if (alive) setState({ loading: false, error: null, data: d })
      })
      .catch((e) => {
        if (alive) setState({ loading: false, error: errMessage(e, '加载失败'), data: null })
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  return { ...state, reload: () => setNonce((n) => n + 1) }
}

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

/** 当前律师配置了凭证的 OA 站点 */
export function useOAConfigs() {
  return useLoad<OAConfig[]>(() => listOAConfigs(), [])
}

/**
 * 利益冲突预检 —— 手动触发（POST，且有副作用：会写审计）。
 * 不做成 useLoad：进页面就自动跑一次冲突检查没有意义，
 * 那是「立案前才该做的动作」，且每次都落一条审计记录。
 */
export function useConflictCheck(caseId: number | null) {
  const [state, setState] = useState<AsyncState<ConflictCheck>>({
    loading: false,
    error: null,
    data: null,
  })

  const run = async () => {
    if (!caseId) return
    setState({ loading: true, error: null, data: null })
    try {
      const d = await runConflictCheck(caseId)
      setState({ loading: false, error: null, data: d })
    } catch (e) {
      setState({ loading: false, error: errMessage(e, '加载失败'), data: null })
    }
  }

  return { ...state, run, reset: () => setState({ loading: false, error: null, data: null }) }
}
