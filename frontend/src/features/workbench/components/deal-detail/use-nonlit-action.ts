/**
 * 非诉阶段动作状态机（与诉讼线 `use-stage-action` 同构）
 *
 * 单独成文件：react-refresh 要求一个文件只导出组件，hook 与组件混在一起会
 * 让热更新失效（本仓库 eslint 对这条是 error 级）。
 */

import { useCallback, useEffect, useRef, useState } from 'react'

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
  /**
   * 跑批代币：`execute` 开头领一个新号，链条每推进一步比对一次，号变了就退出。
   *
   * 为什么不用布尔 `aborted`：`reset()` 既要中止在跑的链条，又不能影响随后的
   * 下一次 `execute()`——布尔只能靠 `setTimeout(0)` 复位，而那条 0ms 回调会先于
   * 链条里 `await sleep(...)` 的续行执行，于是刚置的中止标记立刻被清掉，`reset()`
   * 实际上中止不了任何东西（除了同一 tick 内还被检查到的场景）。代币没有「复位」
   * 这个动作：新 `execute` 领新号，自然与旧链条断开。
   */
  const runIdRef = useRef(0)

  /** 中止在跑的链条（置空 resume 让 `await confirm` 不悬着，代币作废让链条下次检查即退出） */
  const abortCurrentRun = useCallback(() => {
    runIdRef.current++
    const resume = resumeRef.current
    resumeRef.current = null
    resume?.()
  }, [])

  /** 卸载中止：链条里有多处 `await sleep()`，没有这一句就会对已卸载组件继续 setState */
  useEffect(() => () => abortCurrentRun(), [abortCurrentRun])

  const reset = useCallback(() => {
    abortCurrentRun()
    setPhase('idle')
    setPercent(0)
    setProgress('')
    setStepIndex(0)
    setConfirmText('')
    setLog([])
    setRetries(0)
  }, [abortCurrentRun])

  const confirm = useCallback(() => {
    const fn = resumeRef.current
    resumeRef.current = null
    if (fn) fn()
  }, [])

  const execute = useCallback(async () => {
    const runId = ++runIdRef.current
    /** 本代是否仍是当前代（reset / 卸载 / 新一次 execute 都会让旧代失效） */
    const alive = () => runIdRef.current === runId
    setPhase('running')
    setLog([])
    setPercent(0)
    setRetries(0)

    const weights = steps.map((s) => Math.max(1, s.ms ?? 400))
    const total = weights.reduce((a, b) => a + b, 0)
    let acc = 0
    let rt = 0

    for (let i = 0; i < steps.length; i++) {
      if (!alive()) return
      const s = steps[i]!
      const w = weights[i]!
      const from = (acc / total) * 100
      const to = ((acc + w) / total) * 100

      setStepIndex(i + 1)
      setProgress(s.text)

      // 并行子任务
      if (s.parallel?.length) {
        for (const sub of s.parallel) {
          if (!alive()) return
          setLog((v) => [...v, { at: clock(), text: `  ↳ ${sub}`, kind: 'sub' }])
          await sleep(jitter(Math.max(120, w / (s.parallel.length + 1))))
        }
      }

      // 重试
      if (s.retry) {
        for (let t = 0; t < s.retry.times; t++) {
          if (!alive()) return
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
        if (!alive()) return
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
        if (!alive()) return
        setLog((v) => [...v, { at: clock(), text: '已确认，继续', kind: 'ok' }])
        setPhase('running')
        setConfirmText('')
      }

      acc += w
    }

    if (!alive()) return
    setPhase('done')
    setPercent(100)
    setProgress('')
    setLog((v) => [...v, { at: clock(), text: '完成', kind: 'ok' }])
  }, [steps])

  return { phase, percent, progress, stepIndex, confirmText, log, retries, summary, execute, reset, confirm }
}
