import { useCallback, useRef, useState } from 'react'

import { usePollSession, type PollLease } from '@/hooks/use-poll-session'

import { getTask, recognizeFile, retryTask } from '../api'
import {
  NOT_FOUND_GRACE_POLLS,
  RECOGNIZE_MAX_POLLS,
  RECOGNIZE_POLL_MS,
  SLOW_HINT_AFTER_SECONDS,
  STALLED_HINT_AFTER_SECONDS,
} from '../constants'
import type { TaskOut } from '../types'

/** 识别流程阶段 */
export type RecognizePhase = 'idle' | 'submitting' | 'polling' | 'ready' | 'error'

/** 进行中/失败时给用户的诊断信息（用于替换「只知道转圈」的旧体验） */
export interface RecognizeProgressInfo {
  /** 已等待秒数（前端自己数，不依赖后端时间精度） */
  elapsedSeconds: number
  /**
   * 等待感受分级：
   * - normal  正常范围（< 10s），只说"通常 5-30 秒"
   * - slow    偏慢（≥10s），提示"比平时慢"
   * - stalled 疑似卡住（≥60s 或后端标记 stalled），给"可重试"出口
   */
  level: 'normal' | 'slow' | 'stalled'
  /** 后端判定疑似僵死（processing 且耗时超阈值） */
  backendStalled: boolean
}

export interface UseRecognizeResult {
  phase: RecognizePhase
  hint: string
  error: string | null
  task: TaskOut | null
  progress: RecognizeProgressInfo
  /** 上传并识别到终态（success/failed） */
  submit: (file: File) => Promise<void>
  /** 重跑当前任务（复用已上传文件，不重传） */
  retry: () => Promise<void>
  /** 是否可重试（失败或疑似卡住时） */
  canRetry: boolean
  retrying: boolean
  /** 绑定 / 确认后刷新任务态 */
  refresh: () => Promise<void>
  reset: () => void
}

const IDLE_PROGRESS: RecognizeProgressInfo = { elapsedSeconds: 0, level: 'normal', backendStalled: false }

/**
 * 文书识别编排：上传 → 轮询任务到终态。
 *
 * 轮询用 setTimeout 串行 + 会话号守卫（usePollSession）：重提交 / reset / 卸载
 * 都让旧循环在下一个自检点退出，旧任务迟到的终态不会覆盖新提交
 * （旧 cancelled ref 只管卸载，管不住 submit 重入，见 use-poll-session.ts 头注释）。
 * 404 宽限 15 轮（django-q worker 摘任务到落库有空窗），单轮失败不判死。
 *
 * **为什么加 elapsed / level / retry**（2026-10-28 真实事故）：
 * 本机 Clash 把内网 LLM 网关当成外网走代理，调用持续 502 后一路重试，
 * 单次识别实测 439 秒。而界面从第 1 秒到第 439 秒都只显示「识别中…通常 5-30 秒」，
 * 用户完全无法判断是"还在正常跑"还是"已经死了"，也没有任何重试出口 ——
 * 只能关弹窗重新上传。现在：
 *   1. 显示真实已等待时长，超过 10s / 60s 分别升级文案；
 *   2. 后端 `stalled` 标记（processing 且超阈值）一到就直说"可能卡住了"；
 *   3. 失败或疑似卡住时给「重试」按钮，复用已上传文件，不必重传。
 */
export function useRecognize(): UseRecognizeResult {
  const [phase, setPhase] = useState<RecognizePhase>('idle')
  const [error, setError] = useState<string | null>(null)
  const [task, setTask] = useState<TaskOut | null>(null)
  const [progress, setProgress] = useState<RecognizeProgressInfo>(IDLE_PROGRESS)
  const [retrying, setRetrying] = useState(false)
  // taskId 同时用 ref（给异步循环读最新值，避免闭包陈旧）与 state（给渲染读，
  // 否则 ref 变更不触发重渲染，canRetry 会一直是旧值 —— eslint react-hooks/refs）
  const taskId = useRef<number | null>(null)
  const [activeTaskId, setActiveTaskId] = useState<number | null>(null)
  const pollSession = usePollSession()

  const refresh = useCallback(async () => {
    if (taskId.current == null) return
    setTask(await getTask(taskId.current))
  }, [])

  /** 轮询任务到终态；lease 由 submit 签发，重提交/卸载后旧循环即刻自检退出 */
  const poll = useCallback(async (id: number, lease: PollLease) => {
    let notFoundStreak = 0
    let waitedMs = 0

    for (let i = 0; i < RECOGNIZE_MAX_POLLS; i++) {
      if (lease.isStale()) return

      // 每轮先推进本地计时：后端请求本身可能很慢，不能只靠响应到达才更新
      const elapsedSeconds = Math.round(waitedMs / 1000)
      setProgress((prev) => ({
        elapsedSeconds,
        level:
          elapsedSeconds >= STALLED_HINT_AFTER_SECONDS
            ? 'stalled'
            : elapsedSeconds >= SLOW_HINT_AFTER_SECONDS
              ? 'slow'
              : 'normal',
        backendStalled: prev.backendStalled,
      }))

      try {
        const t = await getTask(id)
        if (lease.isStale()) return
        if (t.status === 'success') {
          setTask(t)
          setPhase('ready')
          setProgress(IDLE_PROGRESS)
          return
        }
        if (t.status === 'failed') {
          setError(t.error_message || '识别失败')
          setPhase('error')
          return
        }
        notFoundStreak = 0
        // 后端判定的僵死比前端计时更权威（它知道 worker 是否真拉起过）
        if (t.stalled) {
          setProgress((prev) => ({ ...prev, level: 'stalled', backendStalled: true }))
        }
      } catch (e) {
        if (lease.isStale()) return
        const status = (e as { response?: { status?: number } })?.response?.status
        if (status === 404) {
          notFoundStreak++
          if (notFoundStreak >= NOT_FOUND_GRACE_POLLS) {
            setError('识别任务排队后没有执行起来——多为后台 worker 未运行，请稍后重试')
            setPhase('error')
            return
          }
        }
        // 其他单轮失败不判死，继续等
      }

      await lease.sleep(RECOGNIZE_POLL_MS)
      waitedMs += RECOGNIZE_POLL_MS
    }
    if (lease.isStale()) return
    setError('识别超时（超过 10 分钟仍无结果），可点「重试」再跑一次')
    setPhase('error')
  }, [])

  const submit = useCallback(
    async (file: File) => {
      // 先开新会话再清 state：旧任务正在 await 的轮询从此失效，
      // 迟到的旧终态不会再覆盖本次提交
      const lease = pollSession.begin()
      setTask(null)
      setError(null)
      setProgress(IDLE_PROGRESS)
      setPhase('submitting')
      try {
        const { task_id: id } = await recognizeFile(file)
        if (lease.isStale()) return
        taskId.current = id
        setActiveTaskId(id)
        setPhase('polling')
        await poll(id, lease)
      } catch {
        if (lease.isStale()) return
        setError('上传失败，请检查文件格式或稍后重试')
        setPhase('error')
      }
    },
    [poll, pollSession],
  )

  /**
   * 重跑：复用后端已存的同一个文件，不重新上传。
   * 换新 lease 让上一次可能仍在跑的轮询立刻失效，避免两套循环同时写 state。
   */
  const retry = useCallback(async () => {
    const id = taskId.current
    if (id == null) return
    const lease = pollSession.begin()
    setRetrying(true)
    setError(null)
    setProgress(IDLE_PROGRESS)
    setPhase('polling')
    try {
      const t = await retryTask(id)
      if (lease.isStale()) return
      setTask(null)
      // 后端已把任务重置为 pending，进入轮询等它跑到终态
      if (t.status === 'success') {
        setTask(t)
        setPhase('ready')
        return
      }
      await poll(id, lease)
    } catch {
      if (lease.isStale()) return
      setError('重试失败，请关闭后重新上传文书')
      setPhase('error')
    } finally {
      setRetrying(false)
    }
  }, [poll, pollSession])

  const reset = useCallback(() => {
    // 只失效会话：旧轮询自检退出（不再打接口），state 全部归零
    pollSession.invalidate()
    taskId.current = null
    setActiveTaskId(null)
    setTask(null)
    setError(null)
    setProgress(IDLE_PROGRESS)
    setRetrying(false)
    setPhase('idle')
  }, [pollSession])

  const hint =
    phase === 'submitting'
      ? '正在上传文书…'
      : phase === 'polling'
        ? pollingHint(progress)
        : ''

  // 失败可重试；疑似卡住也允许（后端会二次校验任务是否真的僵死）
  const canRetry = activeTaskId != null && (phase === 'error' || progress.level === 'stalled')

  return { phase, hint, error, task, progress, submit, retry, canRetry, retrying, refresh, reset }
}

/**
 * 轮询中的提示文案：随已等待时长升级，让用户知道「慢」和「卡死」的区别。
 *
 * 基准（正常 1-3 秒，含 LLM 分析通常 5-30 秒）来自真实识别耗时分布；
 * 超过 60 秒基本只在出问题时才发生，所以那时直接把重试出口亮出来。
 */
function pollingHint(p: RecognizeProgressInfo): string {
  const s = p.elapsedSeconds
  if (p.backendStalled || p.level === 'stalled') {
    return `已等待 ${s} 秒，比正常慢很多，可能卡住了——可点「重试」再跑一次`
  }
  if (p.level === 'slow') {
    return `识别中…已等待 ${s} 秒（比平时慢，可能需要排队）`
  }
  return '识别中（文本提取 + LLM 分析），通常 5-30 秒…'
}
