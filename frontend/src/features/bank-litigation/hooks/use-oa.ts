import { useState } from 'react'

import { errMessage } from '@/lib/errors'

import { listOAConfigs, runConflictCheck, type ConflictCheck, type OAConfig } from '../api'

import { useLoad, type AsyncState } from './use-async-load'

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
