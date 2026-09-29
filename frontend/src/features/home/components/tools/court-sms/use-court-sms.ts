import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import {
  assignCourtSmsCase,
  getCourtSmsDetail,
  retryCourtSms,
  submitCourtSms,
  type CourtSmsDetail,
} from '../../../api'
import { HOME_INBOX_KEY } from '../../../api'
import { smsStageInfo, SMS_STAGES, type SmsTerminal } from './stages'

/** 轮询节奏：2s 一拍，与 doc-parse / doc-converter 一致 */
const POLL_MS = 2000
/** 轮询上限：法院下载走爬虫可能要几分钟，给到 10 分钟后转「后台继续，可稍后查看」 */
const MAX_POLLS = 300
/** 详情查询连续失败宽限：偶发网络抖动不当场判死 */
const MAX_QUERY_ERRORS = 10

/** 弹窗编排阶段：idle 未提交 / submitting 提交中 / processing 处理中(轮询) / done 终态 / timeout 等待超时 */
export type SmsPhase = 'idle' | 'submitting' | 'processing' | 'done' | 'timeout'

export interface CourtSmsFlowState {
  phase: SmsPhase
  /** 终态语义（phase=done 时有值） */
  outcome: SmsTerminal | null
  smsId: number | null
  /** 最近一次详情（步进器 / 结果区渲染用；提交瞬间可能还没有） */
  detail: CourtSmsDetail | null
  /** 观测到的最大阶段下标（failed 时状态机不告诉停在哪步，用它兜底） */
  stage: number
  /** 提交动作本身的失败（后端没建出记录，没有 id 可轮询） */
  submitError: string | null
  /** assign / retry 按钮的 busy */
  actionBusy: boolean
}

export interface UseCourtSmsResult extends CourtSmsFlowState {
  submit: (content: string) => Promise<boolean>
  /** 人工分配案件；成功后回到 processing 继续轮询到终态 */
  assignCase: (caseId: number) => Promise<void>
  /** 重新处理；同样回到 processing */
  retry: () => Promise<void>
  /** 超时后继续等待（只恢复轮询，不重跑后端流程） */
  resume: () => void
  /** 重开弹窗时拉一次最新详情；非终态则续上轮询 */
  refresh: () => Promise<void>
  /** 清空流程（回到 idle） */
  reset: () => void
}

/**
 * 法院短信全流程编排：提交 → 轮询详情 → 终态(completed/failed/pending_manual)。
 * 人工分配 / 重试后状态会回到 renaming/notifying，自动续轮询。
 * 轮询挂在 hook 上而不是弹窗上：用户关掉弹窗流程照跑，卡片上可随时重开查看。
 */
export function useCourtSms(): UseCourtSmsResult {
  const [state, setState] = useState<CourtSmsFlowState>({
    phase: 'idle',
    outcome: null,
    smsId: null,
    detail: null,
    stage: 0,
    submitError: null,
    actionBusy: false,
  })
  const timer = useRef(0)
  const cancelled = useRef(false)
  // 阶段只进不退：failed 时后端不知道停在哪步，用观测到的最大阶段兜底展示
  const maxStage = useRef(0)
  const queryClient = useQueryClient()

  useEffect(() => {
    cancelled.current = false
    return () => {
      cancelled.current = true
      window.clearTimeout(timer.current)
    }
  }, [])

  const sleep = (ms: number) =>
    new Promise<void>((resolve) => {
      timer.current = window.setTimeout(resolve, ms)
    })

  const invalidateInbox = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: HOME_INBOX_KEY })
  }, [queryClient])

  const poll = useCallback(async (smsId: number) => {
    let queryErrors = 0
    for (let i = 0; i < MAX_POLLS; i++) {
      if (cancelled.current) return
      try {
        const detail = await getCourtSmsDetail(smsId)
        if (cancelled.current) return
        queryErrors = 0
        const info = smsStageInfo(detail.status)
        maxStage.current = Math.max(maxStage.current, info.stage)
        const terminal = info.terminal
        setState((s) => ({ ...s, detail, stage: maxStage.current, phase: terminal ? 'done' : 'processing', outcome: terminal }))
        if (terminal) {
          invalidateInbox()
          return
        }
      } catch {
        if (cancelled.current) return
        // 短信刚创建就查询可能撞上瞬时错误；连续失败才放弃
        queryErrors += 1
        if (queryErrors >= MAX_QUERY_ERRORS) {
          setState((s) => ({ ...s, phase: 'timeout', outcome: null }))
          return
        }
      }
      await sleep(POLL_MS)
    }
    if (cancelled.current) return
    // 10 分钟仍在跑：不判失败，后台会继续；收件箱稍后会有结果
    setState((s) => ({ ...s, phase: 'timeout', outcome: null }))
  }, [invalidateInbox])

  const submit = useCallback(
    async (content: string) => {
      window.clearTimeout(timer.current)
      maxStage.current = 0
      setState({
        phase: 'submitting',
        outcome: null,
        smsId: null,
        detail: null,
        stage: 0,
        submitError: null,
        actionBusy: false,
      })
      try {
        const id = await submitCourtSms(content)
        if (cancelled.current) return false
        setState((s) => ({ ...s, phase: 'processing', smsId: id }))
        void poll(id)
        return true
      } catch (e) {
        if (cancelled.current) return false
        setState({
          phase: 'done',
          outcome: 'failed',
          smsId: null,
          detail: null,
          stage: 0,
          submitError: e instanceof Error ? e.message : '短信提交失败，请稍后重试',
          actionBusy: false,
        })
        return false
      }
    },
    [poll],
  )

  const assignCase = useCallback(
    async (caseId: number) => {
      const smsId = state.smsId
      if (!smsId) return
      setState((s) => ({ ...s, actionBusy: true }))
      try {
        await assignCourtSmsCase(smsId, caseId)
        if (cancelled.current) return
        // 分配成功 → 后端进入 renaming/notifying，继续轮询到终态
        setState((s) => ({ ...s, actionBusy: false, phase: 'processing', outcome: null }))
        void poll(smsId)
      } catch {
        if (cancelled.current) return
        setState((s) => ({ ...s, actionBusy: false }))
        throw new Error('指定案件失败，请重试')
      }
    },
    [poll, state.smsId],
  )

  const retry = useCallback(async () => {
    const smsId = state.smsId
    if (!smsId) return
    setState((s) => ({ ...s, actionBusy: true }))
    try {
      await retryCourtSms(smsId)
    } finally {
      if (!cancelled.current) setState((s) => ({ ...s, actionBusy: false }))
    }
    if (cancelled.current) return
    maxStage.current = 0
    setState((s) => ({ ...s, phase: 'processing', outcome: null, stage: 0 }))
    void poll(smsId)
  }, [poll, state.smsId])

  const resume = useCallback(() => {
    const smsId = state.smsId
    if (!smsId) return
    setState((s) => ({ ...s, phase: 'processing' }))
    void poll(smsId)
  }, [poll, state.smsId])

  /**
   * 重开弹窗时刷新一次后端状态：弹窗关着的时候流程可能已推进
   * （人工分配被处理 / 自动匹配成功 / 通知发完），终端态尤其会过期。
   * 查询失败保持原状（记录可能已被删）。
   */
  const refresh = useCallback(async () => {
    const smsId = state.smsId
    if (!smsId) return
    try {
      const detail = await getCourtSmsDetail(smsId)
      if (cancelled.current) return
      const info = smsStageInfo(detail.status)
      maxStage.current = Math.max(maxStage.current, info.stage)
      if (info.terminal) {
        setState((s) => ({ ...s, detail, stage: maxStage.current, phase: 'done', outcome: info.terminal }))
        invalidateInbox()
      } else {
        // 后端还在跑（或被重试），续上轮询
        setState((s) => ({ ...s, detail, stage: maxStage.current, phase: 'processing', outcome: null }))
        void poll(smsId)
      }
    } catch {
      // 保持原状态
    }
  }, [invalidateInbox, poll, state.smsId])

  const reset = useCallback(() => {
    window.clearTimeout(timer.current)
    maxStage.current = 0
    setState({
      phase: 'idle',
      outcome: null,
      smsId: null,
      detail: null,
      stage: 0,
      submitError: null,
      actionBusy: false,
    })
  }, [])

  return { ...state, submit, assignCase, retry, resume, refresh, reset }
}

/** 详情 + 观测最大阶段 → 步进器要用的 (steps 当前下标, failedAt) */
export function stageForDisplay(
  detail: CourtSmsDetail | null,
  maxStage: number,
): { current: number; failedAt: number | null } {
  if (!detail) return { current: 0, failedAt: null }
  const info = smsStageInfo(detail.status)
  if (info.terminal === 'completed') return { current: SMS_STAGES.length, failedAt: null }
  if (info.failedAt !== null) return { current: info.failedAt, failedAt: info.failedAt }
  return { current: Math.max(maxStage, info.stage), failedAt: null }
}
