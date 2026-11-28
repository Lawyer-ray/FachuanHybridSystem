import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { errMessage } from '@/lib/errors'

import {
  abortCourtSmsTask,
  assignCourtSmsCase,
  getCourtSmsDetail,
  retryCourtSms,
  submitCourtSms,
  uploadCourtSmsMaterials,
} from '../../../api'
import { HOME_INBOX_KEY, courtSmsHistoryKeys } from '../../../api'
import { smsStageInfo } from './stages'
import type { CourtSmsFlowState, SmsSource, UseCourtSmsResult } from './types'

/** 轮询节奏：2s 一拍，与 doc-parse / doc-converter 一致 */
const POLL_MS = 2000
/** 轮询上限：法院下载走爬虫可能要几分钟，给到 10 分钟后转「后台继续，可稍后查看」 */
const MAX_POLLS = 300
/** 详情查询连续失败宽限：偶发网络抖动不当场判死 */
const MAX_QUERY_ERRORS = 10

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
    source: 'sms',
    intake: null,
  })
  const timer = useRef(0)
  const cancelled = useRef(false)
  // 阶段只进不退：failed 时后端不知道停在哪步，用观测到的最大阶段兜底展示
  const maxStage = useRef(0)
  // 轮询会话号：每次开启新轮询自增；旧轮询发现会话号变了（重试/中止/重开）
  // 就自行退出，避免被删除的记录还在 404 计数、把 UI 拖回 timeout 幽灵态
  const pollSession = useRef(0)
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

  // 收件箱卡片与历史弹窗都要失效：终态/删除/刷新都会改变历史列表的内容
  const invalidateInbox = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: HOME_INBOX_KEY })
    void queryClient.invalidateQueries({ queryKey: courtSmsHistoryKeys.all })
  }, [queryClient])

  const poll = useCallback(
    async (smsId: number) => {
      const session = ++pollSession.current
      const isStale = () => cancelled.current || session !== pollSession.current
      let queryErrors = 0
      for (let i = 0; i < MAX_POLLS; i++) {
        if (isStale()) return
        try {
          const detail = await getCourtSmsDetail(smsId)
          if (isStale()) return
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
          if (isStale()) return
          // 短信刚创建就查询可能撞上瞬时错误；连续失败才放弃
          queryErrors += 1
          if (queryErrors >= MAX_QUERY_ERRORS) {
            setState((s) => ({ ...s, phase: 'timeout', outcome: null }))
            return
          }
        }
        await sleep(POLL_MS)
      }
      if (isStale()) return
      // 10 分钟仍在跑：不判失败，后台会继续；收件箱稍后会有结果
      setState((s) => ({ ...s, phase: 'timeout', outcome: null }))
    },
    [invalidateInbox],
  )

  const resetForSubmit = useCallback((source: SmsSource) => {
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
      source,
      intake: null,
    })
  }, [])

  const failSubmit = useCallback((message: string) => {
    setState((s) => ({
      ...s,
      phase: 'done',
      outcome: 'failed',
      smsId: null,
      detail: null,
      stage: 0,
      submitError: message,
      actionBusy: false,
    }))
  }, [])

  const submit = useCallback(
    async (content: string) => {
      resetForSubmit('sms')
      try {
        const id = await submitCourtSms(content)
        if (cancelled.current) return false
        setState((s) => ({ ...s, phase: 'processing', smsId: id }))
        void poll(id)
        return true
      } catch (e) {
        if (cancelled.current) return false
        failSubmit(errMessage(e, '短信提交失败，请稍后重试'))
        return false
      }
    },
    [failSubmit, poll, resetForSubmit],
  )

  /**
   * 提交客户转交的材料：与 submit 走同一套编排（提交 → 轮询 → 终态），
   * 仅来源不同。材料入库明细（哪些被跳过）随提交结果交给弹窗展示。
   */
  const submitFiles = useCallback(
    async (files: File[], note?: string) => {
      resetForSubmit('material')
      try {
        const { id, materials } = await uploadCourtSmsMaterials(files, note)
        if (cancelled.current) return false
        setState((s) => ({ ...s, phase: 'processing', smsId: id, intake: materials }))
        void poll(id)
        return true
      } catch (e) {
        if (cancelled.current) return false
        failSubmit(errMessage(e, '材料提交失败，请稍后重试'))
        return false
      }
    },
    [failSubmit, poll, resetForSubmit],
  )

  const openExisting = useCallback(
    (smsId: number) => {
      window.clearTimeout(timer.current)
      maxStage.current = 0
      setState({
        phase: 'processing',
        outcome: null,
        smsId,
        detail: null,
        stage: 0,
        submitError: null,
        actionBusy: false,
        // 历史列表进来的记录来源未知，按短信通道文案展示（详情里有无下载链接可见）
        source: 'sms',
        intake: null,
      })
      void poll(smsId)
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

  const reset = useCallback(() => {
    // 会话号自增让旧轮询自然退出（记录被删后轮询只会 404 计数拖回 timeout）
    pollSession.current++
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
      source: 'sms',
      intake: null,
    })
  }, [])

  /**
   * 终止并彻底删除任务：后端会清掉 Django-Q 重试调度/排队任务并删除短信
   * 记录。成功后流程回 idle；失败（网络/权限）抛给调用方提示，状态保持。
   */
  const abortAndRemove = useCallback(async () => {
    const smsId = state.smsId
    if (!smsId) return
    setState((s) => ({ ...s, actionBusy: true }))
    try {
      await abortCourtSmsTask(smsId)
    } catch (e) {
      if (!cancelled.current) setState((s) => ({ ...s, actionBusy: false }))
      throw e
    }
    if (cancelled.current) return
    reset()
    invalidateInbox()
  }, [invalidateInbox, reset, state.smsId])

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

  return { ...state, submit, submitFiles, openExisting, assignCase, retry, resume, abortAndRemove, refresh, reset }
}
