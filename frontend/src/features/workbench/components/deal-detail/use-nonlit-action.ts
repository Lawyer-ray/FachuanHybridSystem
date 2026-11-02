/**
 * 非诉阶段动作状态机（与诉讼线 `use-stage-action` 同构）
 *
 * 单独成文件：react-refresh 要求一个文件只导出组件，hook 与组件混在一起会
 * 让热更新失效（本仓库 eslint 对这条是 error 级）。
 */

import { useCallback, useRef, useState } from 'react'

export type NonLitPhase = 'idle' | 'running' | 'awaiting' | 'done' | 'failed'

export interface NonLitLogLine {
  at: string
  text: string
  kind?: 'info' | 'ok' | 'warn' | 'error' | 'sub'
}

export interface NonLitStep {
  text: string
  ms?: number
  retry?: { times: number; delay: number; reason: string }
  parallel?: string[]
  confirm?: string
}

function clock(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
const jitter = (ms: number) => Math.round(ms * (0.7 + Math.random() * 0.6))

export function useNonLitAction(steps: NonLitStep[], summary: string) {
  const [phase, setPhase] = useState<NonLitPhase>('idle')
  const [percent, setPercent] = useState(0)
  const [progress, setProgress] = useState('')
  const [stepIndex, setStepIndex] = useState(0)
  const [confirmText, setConfirmText] = useState('')
  const [log, setLog] = useState<NonLitLogLine[]>([])
  const [retries, setRetries] = useState(0)
  const resumeRef = useRef<(() => void) | null>(null)
  const aborted = useRef(false)

  const reset = useCallback(() => {
    aborted.current = true
    resumeRef.current = null
    setPhase('idle')
    setPercent(0)
    setProgress('')
    setStepIndex(0)
    setConfirmText('')
    setLog([])
    setRetries(0)
    setTimeout(() => { aborted.current = false }, 0)
  }, [])

  const confirm = useCallback(() => {
    const fn = resumeRef.current
    resumeRef.current = null
    if (fn) fn()
  }, [])

  const execute = useCallback(async () => {
    aborted.current = false
    setPhase('running')
    setLog([])
    setPercent(0)
    setRetries(0)

    const weights = steps.map((s) => Math.max(1, s.ms ?? 400))
    const total = weights.reduce((a, b) => a + b, 0)
    let acc = 0
    let rt = 0

    for (let i = 0; i < steps.length; i++) {
      if (aborted.current) return
      const s = steps[i]!
      const w = weights[i]!
      const from = (acc / total) * 100
      const to = ((acc + w) / total) * 100

      setStepIndex(i + 1)
      setProgress(s.text)

      // 并行子任务
      if (s.parallel?.length) {
        for (const sub of s.parallel) {
          if (aborted.current) return
          setLog((v) => [...v, { at: clock(), text: `  ↳ ${sub}`, kind: 'sub' }])
          await sleep(jitter(Math.max(120, w / (s.parallel.length + 1))))
        }
      }

      // 重试
      if (s.retry) {
        for (let t = 0; t < s.retry.times; t++) {
          if (aborted.current) return
          rt++
          setRetries(rt)
          setLog((v) => [...v, { at: clock(), text: `${s.retry!.reason}（第 ${t + 1} 次重试）`, kind: 'warn' }])
          setProgress(`重试中 ${t + 1}/${s.retry.times}…`)
          await sleep(jitter(s.retry.delay))
        }
        setLog((v) => [...v, { at: clock(), text: `重试成功 · ${s.text}`, kind: 'ok' }])
      } else {
        setLog((v) => [...v, { at: clock(), text: s.text, kind: 'info' }])
      }

      // 平滑推进
      for (let k = 1; k <= 6; k++) {
        if (aborted.current) return
        setPercent(Math.round(from + ((to - from) * k) / 6))
        await sleep(jitter(Math.max(40, w / 9)))
      }

      // 等人确认
      if (s.confirm) {
        setPhase('awaiting')
        setPercent(Math.round(to))
        setProgress('')
        setConfirmText(s.confirm)
        await new Promise<void>((res) => { resumeRef.current = res })
        if (aborted.current) return
        setLog((v) => [...v, { at: clock(), text: '已确认，继续', kind: 'ok' }])
        setPhase('running')
        setConfirmText('')
      }

      acc += w
    }

    if (aborted.current) return
    setPhase('done')
    setPercent(100)
    setProgress('')
    setLog((v) => [...v, { at: clock(), text: '完成', kind: 'ok' }])
  }, [steps])

  return { phase, percent, progress, stepIndex, confirmText, log, retries, summary, execute, reset, confirm }
}
