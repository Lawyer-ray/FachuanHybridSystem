/**
 * 阶段动作引擎（v2）—— 让"机器在干活"这件事看起来是真的
 *
 * ═══ v1 的问题 ═══
 * v1 只是「6 步 setTimeout 顺序跑完」，看起来像进度条刷一遍：
 *   · 每步耗时恒定，节奏均匀 —— 真系统不会这样
 *   · 没有百分比、没有子任务并行、没有重试、没有中断等人
 *   · 失败只能整个重来，不像真实的「这一步失败、重试两次后成功」
 *
 * ═══ v2 加的四个真实感要素 ═══
 *   ① **可变耗时 + 进度百分比**：每步有自己的权重与波动，进度条平滑推进
 *   ② **失败-重试循环**：某步可标记 `retry: { times, delay, reason }`，
 *      演示时会先报错、等待、自动重试，最后成功（或最终失败）
 *   ③ **中断等人（confirm）**：某步可 `confirm: '要人工确认的话术'`，
 *      执行到这里会停下等律师点「确认」，点了才继续 —— 这是最真实的形态
 *   ④ **并行子任务**：某步可 `parallel: ['子任务A','子任务B']`，
 *      日志里会交错出现，像真的多线程在处理
 *
 * ═══ 为什么用 setTimeout 而不是真接口 ═══
 * 演示场景下要的是**可预期的节奏**；真接口的快慢取决于网络，讲解时会跳。
 * 所以耗时是剧本化的，但**失败/重试/中断的语义是真的**：
 * 状态机本身能正确停在 failed / awaiting，不是假装。
 */

import { useCallback, useRef, useState } from 'react'

export type ActionPhase = 'idle' | 'running' | 'awaiting' | 'done' | 'failed'

export interface ActionLogLine {
  at: string
  text: string
  kind?: 'info' | 'ok' | 'warn' | 'error' | 'sub'
}

/** 一步的剧本 */
export interface ActionStep {
  text: string
  /** 基准耗时（毫秒）。实际会在 ±30% 波动，除非 fixed */
  ms?: number
  /** 关掉耗时波动（关键的短步骤用） */
  fixed?: boolean
  /** 这一步会先失败再重试：times 次后成功 */
  retry?: { times: number; delay: number; reason: string }
  /** 到这一步停下，等人点确认；点完才继续 */
  confirm?: string
  /** 并行子任务：日志里交错出现在本步之下 */
  parallel?: string[]
  /** 这一步必然失败（最终失败，不重试） */
  fail?: string
}

export interface StageActionOptions<T> {
  steps: ActionStep[]
  run?: () => Promise<T>
  toSummary?: (r: T) => string
}

export interface StageActionState {
  phase: ActionPhase
  /** 0-100，按步骤权重推进 */
  percent: number
  /** 当前在做什么 */
  progress: string
  /** 当前是第几步（1-based） */
  stepIndex: number
  /** 中断时等人确认的话术 */
  confirmText: string
  summary: string
  error: string
  log: ActionLogLine[]
  /** 已重试次数（展示用） */
  retries: number
}

const INITIAL: StageActionState = {
  phase: 'idle',
  percent: 0,
  progress: '',
  stepIndex: 0,
  confirmText: '',
  summary: '',
  error: '',
  log: [],
  retries: 0,
}

function clock(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** 耗时波动 ±30%，模拟真实系统的抖动 */
function jitter(ms: number, fixed?: boolean): number {
  if (fixed) return ms
  const factor = 0.7 + Math.random() * 0.6
  return Math.round(ms * factor)
}

export function useStageAction<T>({ steps, run, toSummary }: StageActionOptions<T>) {
  const [state, setState] = useState<StageActionState>(INITIAL)
  /** 中断时挂起的「继续」回调 */
  const resumeRef = useRef<(() => void) | null>(null)
  /** 中止标记：reset 时置 true，避免旧的 async 继续写状态 */
  const abortedRef = useRef(false)

  const pushLog = useCallback((line: ActionLogLine) => {
    setState((v) => ({ ...v, log: [...v.log, line] }))
  }, [])

  const reset = useCallback(() => {
    abortedRef.current = true
    resumeRef.current = null
    setState(INITIAL)
    setTimeout(() => {
      abortedRef.current = false
    }, 0)
  }, [])

  /** 中断后由「确认」按钮调用 */
  const confirm = useCallback(() => {
    const fn = resumeRef.current
    resumeRef.current = null
    if (fn) fn()
  }, [])

  const execute = useCallback(async () => {
    abortedRef.current = false
    setState({ ...INITIAL, phase: 'running' })

    // 权重：按每步的 ms 分配，没有则默认 1
    const weights = steps.map((s) => Math.max(1, s.ms ?? 320))
    const total = weights.reduce((a, b) => a + b, 0)
    let acc = 0
    let retries = 0

    for (let i = 0; i < steps.length; i++) {
      if (abortedRef.current) return
      const s = steps[i]!
      const w = weights[i]!
      const from = (acc / total) * 100
      const to = ((acc + w) / total) * 100

      setState((v) => ({ ...v, stepIndex: i + 1, progress: s.text, percent: Math.round(from) }))

      // ① 并行子任务：交错出现，像多线程
      if (s.parallel?.length) {
        for (const sub of s.parallel) {
          if (abortedRef.current) return
          pushLog({ at: clock(), text: `  ↳ ${sub}`, kind: 'sub' })
          await sleep(jitter(Math.max(120, w / (s.parallel.length + 1))))
        }
      }

      // ② 必然失败（不重试）
      if (s.fail) {
        pushLog({ at: clock(), text: s.fail, kind: 'error' })
        setState((v) => ({
          ...v,
          phase: 'failed',
          percent: Math.round(to),
          progress: '',
          error: s.fail!,
          retries,
        }))
        return
      }

      // ③ 失败 → 等待 → 重试
      if (s.retry) {
        for (let t = 0; t < s.retry.times; t++) {
          if (abortedRef.current) return
          retries++
          pushLog({ at: clock(), text: `${s.retry.reason}（第 ${t + 1} 次重试）`, kind: 'warn' })
          setState((v) => ({ ...v, retries, progress: `重试中 ${t + 1}/${s.retry!.times}…` }))
          await sleep(jitter(s.retry.delay))
        }
        pushLog({ at: clock(), text: `重试成功 · ${s.text}`, kind: 'ok' })
      } else {
        pushLog({ at: clock(), text: s.text, kind: 'info' })
      }

      // ④ 进度平滑推进（分 6 段，看起来在动而不是跳）
      const segs = 6
      for (let k = 1; k <= segs; k++) {
        if (abortedRef.current) return
        const p = from + ((to - from) * k) / segs
        setState((v) => ({ ...v, percent: Math.round(p) }))
        await sleep(jitter(Math.max(40, w / segs / 1.6), s.fixed))
      }

      // ⑤ 中断等人
      if (s.confirm) {
        setState((v) => ({
          ...v,
          phase: 'awaiting',
          percent: Math.round(to),
          progress: '',
          confirmText: s.confirm!,
        }))
        await new Promise<void>((resolve) => {
          resumeRef.current = resolve
        })
        if (abortedRef.current) return
        pushLog({ at: clock(), text: '已确认，继续', kind: 'ok' })
        setState((v) => ({ ...v, phase: 'running', confirmText: '' }))
      }

      acc += w
    }

    if (abortedRef.current) return

    // 真实接口（如果有）
    try {
      const result = run ? await run() : undefined
      setState((v) => ({
        ...v,
        phase: 'done',
        percent: 100,
        progress: '',
        summary: toSummary && result !== undefined ? toSummary(result) : '已完成',
        retries,
      }))
      pushLog({ at: clock(), text: '完成', kind: 'ok' })
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      pushLog({ at: clock(), text: `失败：${msg}`, kind: 'error' })
      setState((v) => ({ ...v, phase: 'failed', progress: '', error: msg, retries }))
    }
  }, [steps, run, toSummary, pushLog])

  return { ...state, execute, reset, confirm }
}
