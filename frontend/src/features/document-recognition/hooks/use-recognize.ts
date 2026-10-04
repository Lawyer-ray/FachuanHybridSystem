import { useCallback, useRef, useState } from 'react'

import { usePollSession, type PollLease } from '@/hooks/use-poll-session'

import { getTask, recognizeFile } from '../api'
import { NOT_FOUND_GRACE_POLLS, RECOGNIZE_MAX_POLLS, RECOGNIZE_POLL_MS } from '../constants'
import type { TaskOut } from '../types'

/** 识别流程阶段 */
export type RecognizePhase = 'idle' | 'submitting' | 'polling' | 'ready' | 'error'

const PHASE_HINT: Record<RecognizePhase, string> = {
  idle: '',
  submitting: '正在上传文书…',
  polling: '识别中（文本提取 + LLM 分析），通常 5-30 秒…',
  ready: '',
  error: '',
}

export interface UseRecognizeResult {
  phase: RecognizePhase
  hint: string
  error: string | null
  task: TaskOut | null
  /** 上传并识别到终态（success/failed） */
  submit: (file: File) => Promise<void>
  /** 绑定 / 确认后刷新任务态 */
  refresh: () => Promise<void>
  reset: () => void
}

/**
 * 文书识别编排：上传 → 轮询任务到终态。
 *
 * 轮询用 setTimeout 串行 + 会话号守卫（usePollSession）：重提交 / reset / 卸载
 * 都让旧循环在下一个自检点退出，旧任务迟到的终态不会覆盖新提交
 * （旧 cancelled ref 只管卸载，管不住 submit 重入，见 use-poll-session.ts 头注释）。
 * 404 宽限 15 轮（django-q worker 摘任务到落库有空窗），单轮失败不判死。
 */
export function useRecognize(): UseRecognizeResult {
  const [phase, setPhase] = useState<RecognizePhase>('idle')
  const [error, setError] = useState<string | null>(null)
  const [task, setTask] = useState<TaskOut | null>(null)
  const taskId = useRef<number | null>(null)
  const pollSession = usePollSession()

  const refresh = useCallback(async () => {
    if (taskId.current == null) return
    setTask(await getTask(taskId.current))
  }, [])

  /** 轮询任务到终态；lease 由 submit 签发，重提交/卸载后旧循环即刻自检退出 */
  const poll = useCallback(async (id: number, lease: PollLease) => {
    let notFoundStreak = 0
    for (let i = 0; i < RECOGNIZE_MAX_POLLS; i++) {
      if (lease.isStale()) return
      try {
        const t = await getTask(id)
        if (lease.isStale()) return
        if (t.status === 'success') {
          setTask(t)
          setPhase('ready')
          return
        }
        if (t.status === 'failed') {
          setError(t.error_message || '识别失败')
          setPhase('error')
          return
        }
        notFoundStreak = 0
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
    }
    if (lease.isStale()) return
    setError('识别超时（超过 10 分钟仍无结果），请稍后在后台查看任务')
    setPhase('error')
  }, [])

  const submit = useCallback(
    async (file: File) => {
      // 先开新会话再清 state：旧任务正在 await 的轮询从此失效，
      // 迟到的旧终态不会再覆盖本次提交
      const lease = pollSession.begin()
      setTask(null)
      setError(null)
      setPhase('submitting')
      try {
        const { task_id: id } = await recognizeFile(file)
        if (lease.isStale()) return
        taskId.current = id
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

  const reset = useCallback(() => {
    // 只失效会话：旧轮询自检退出（不再打接口），state 全部归零
    pollSession.invalidate()
    taskId.current = null
    setTask(null)
    setError(null)
    setPhase('idle')
  }, [pollSession])

  return { phase, hint: PHASE_HINT[phase], error, task, submit, refresh, reset }
}
