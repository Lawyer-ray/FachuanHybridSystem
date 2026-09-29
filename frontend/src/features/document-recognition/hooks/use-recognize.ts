import { useCallback, useEffect, useRef, useState } from 'react'

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
 * 轮询用 setTimeout 串行 + cancelled ref（组件卸载即停），
 * 404 宽限 15 轮（django-q worker 摘任务到落库有空窗），单轮失败不判死。
 */
export function useRecognize(): UseRecognizeResult {
  const [phase, setPhase] = useState<RecognizePhase>('idle')
  const [error, setError] = useState<string | null>(null)
  const [task, setTask] = useState<TaskOut | null>(null)
  const timer = useRef(0)
  const cancelled = useRef(false)
  const taskId = useRef<number | null>(null)

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

  const refresh = useCallback(async () => {
    if (taskId.current == null) return
    setTask(await getTask(taskId.current))
  }, [])

  const poll = useCallback(async (id: number) => {
    let notFoundStreak = 0
    for (let i = 0; i < RECOGNIZE_MAX_POLLS; i++) {
      if (cancelled.current) return
      try {
        const t = await getTask(id)
        if (cancelled.current) return
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
        if (cancelled.current) return
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
      await sleep(RECOGNIZE_POLL_MS)
    }
    setError('识别超时（超过 10 分钟仍无结果），请稍后在后台查看任务')
    setPhase('error')
  }, [])

  const submit = useCallback(
    async (file: File) => {
      window.clearTimeout(timer.current)
      setTask(null)
      setError(null)
      setPhase('submitting')
      try {
        const { task_id: id } = await recognizeFile(file)
        if (cancelled.current) return
        taskId.current = id
        setPhase('polling')
        await poll(id)
      } catch {
        if (cancelled.current) return
        setError('上传失败，请检查文件格式或稍后重试')
        setPhase('error')
      }
    },
    [poll],
  )

  const reset = useCallback(() => {
    window.clearTimeout(timer.current)
    taskId.current = null
    setTask(null)
    setError(null)
    setPhase('idle')
  }, [])

  return { phase, hint: PHASE_HINT[phase], error, task, submit, refresh, reset }
}
