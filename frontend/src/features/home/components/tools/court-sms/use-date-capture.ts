import { useCallback, useEffect, useRef, useState } from 'react'

import { captureCourtSmsDates, getCourtSmsCaptureStatus, type SourceTasksOut } from '@/features/document-recognition'
import { usePollSession } from '@/hooks/use-poll-session'

/** 轮询节奏：识别通常 5-30 秒，2 秒一拍足够；上限 150 拍（5 分钟）后停手等用户点进来 */
const POLL_MS = 2_000
const MAX_POLLS = 150

type SourceTaskRow = NonNullable<SourceTasksOut['tasks']>[number]

/** 单份文书在旁线上的状态（从识别任务行投影，字段与 SourceTaskOutSchema 对齐） */
export type CaptureTask = SourceTaskRow

export interface DateCaptureState {
  /** 是否已成功发起过送识别（决定气泡是否出现） */
  started: boolean
  /** 发起失败（绑定缺失、文件丢失等）——文案直说，不弹错误对话框 */
  reason: string | null
  tasks: CaptureTask[]
  /** 仍在识别中（有 pending/processing 任务） */
  running: boolean
  /** 待律师确认的候选条数合计 */
  pendingCount: number
  /** 已写入日历的候选条数合计 */
  confirmedCount: number
}

export interface UseDateCaptureResult extends DateCaptureState {
  /** 打开一条短信时调用：自动送识别（幂等）+ 开始轮询到识别结束 */
  start: (smsId: number) => Promise<void>
  /** 「重新识别」：无条件新建任务（force），再次轮询 */
  restart: (smsId: number) => Promise<void>
  /** 确认写入后刷新一次（同步已确认条数） */
  refresh: (smsId: number) => Promise<void>
  /** 停止轮询（弹窗关闭）：不清状态，重开时 start 会再对一次账 */
  stop: () => void
  reset: () => void
}

const IDLE: DateCaptureState = {
  started: false,
  reason: null,
  tasks: [],
  running: false,
  pendingCount: 0,
  confirmedCount: 0,
}

/** 识别任务行的汇总（纯函数，便于单测） */
export function summarize(tasks: CaptureTask[]): Pick<DateCaptureState, 'running' | 'pendingCount' | 'confirmedCount'> {
  const running = tasks.some((t) => t.status === 'pending' || t.status === 'processing')
  return {
    running,
    pendingCount: tasks.reduce((sum, t) => sum + (t.pending_count ?? 0), 0),
    confirmedCount: tasks.reduce((sum, t) => sum + (t.confirmed_count ?? 0), 0),
  }
}

/**
 * 法院短信 → 记一笔的**旁线**编排（与短信主流程完全解耦）。
 *
 * 设计约束（与后端 date_capture_service 对齐）：
 * - 打开短信就自动送识别，不要求用户点按钮；
 * - 幂等：已送过的文书直接复用任务，反复打开弹窗不会重复烧 LLM；
 * - 失败只影响这一段（气泡里给「重试」），**绝不**改变短信主线的状态展示；
 * - 识别为空不是失败：提示律师「这份文书没识别到日期，可手工记一笔」。
 */
export function useDateCapture(): UseDateCaptureResult {
  const [state, setState] = useState<DateCaptureState>(IDLE)
  const pollSession = usePollSession()
  const smsIdRef = useRef<number | null>(null)

  const load = useCallback(
    async (smsId: number, opts?: { force?: boolean }) => {
      const lease = pollSession.begin()
      // 先送（幂等），再从后端拉权威状态：送失败的文书不会出现在状态里
      let reason: string | null = null
      try {
        const res = await captureCourtSmsDates(smsId, { force: opts?.force })
        const skipped = (res.items ?? []).filter((i) => i.action === 'skipped')
        const failed = (res.items ?? []).filter((i) => i.error_message)
        if (skipped.length > 0 && skipped.length === (res.items ?? []).length) {
          reason = skipped[0]?.reason || null
        } else if (failed.length > 0) {
          reason = failed[0]?.error_message || null
        }
      } catch {
        // 送识别本身失败（网络/404）：不阻断短信主线，只在这一段提示
        reason = '送记一笔失败，可稍后重试'
      }
      if (lease.isStale()) return

      for (let i = 0; i < MAX_POLLS; i++) {
        if (lease.isStale()) return
        let tasks: CaptureTask[] = []
        try {
          const res = await getCourtSmsCaptureStatus(smsId)
          tasks = res.tasks ?? []
        } catch {
          // 单轮失败不判死，继续下一拍
        }
        if (lease.isStale()) return

        const summary = summarize(tasks)
        setState({ started: true, reason, tasks, ...summary })
        if (!summary.running) return
        await lease.sleep(POLL_MS)
      }
    },
    [pollSession],
  )

  const start = useCallback(
    async (smsId: number) => {
      smsIdRef.current = smsId
      await load(smsId)
    },
    [load],
  )

  const restart = useCallback(
    async (smsId: number) => {
      smsIdRef.current = smsId
      await load(smsId, { force: true })
    },
    [load],
  )

  /** 确认写入后只刷新状态，不重新送识别（force=false 也是幂等复用，安全） */
  const refresh = useCallback(async (smsId: number) => {
    try {
      const res = await getCourtSmsCaptureStatus(smsId)
      const tasks = res.tasks ?? []
      setState((prev) => ({ ...prev, tasks, ...summarize(tasks) }))
    } catch {
      // 刷新失败保留旧状态，下次轮询/打开时纠正
    }
  }, [])

  const stop = useCallback(() => {
    pollSession.invalidate()
  }, [pollSession])

  const reset = useCallback(() => {
    pollSession.invalidate()
    smsIdRef.current = null
    setState(IDLE)
  }, [pollSession])

  // 卸载兜底：让在飞的轮询自检退出（否则关掉卡片后还在打接口）
  useEffect(() => () => pollSession.invalidate(), [pollSession])

  return { ...state, start, restart, refresh, stop, reset }
}
