/**
 * 阶段动作的通用状态机。
 *
 * ═══ 为什么需要它 ═══
 * 这六个阶段原先全是「预置好的静态展示」：点进去只能看，没有任何可操作的东西。
 * 演示时律师看不出「系统到底做了什么、我该点什么」，整条线像是截图拼的。
 *
 * 每个阶段至少要有一个**由人点击触发**的动作，且动作要呈现三段：
 *   idle（待执行） → running（执行中，带进度文案） → done（已完成，带结果摘要）
 * 失败要能重试，完成要能重置 —— 这是演示时反复讲解所必需的。
 *
 * ═══ 为什么不用 react-query ═══
 * 这些动作是**一次性触发**的，不是要缓存和复用的查询；用 useMutation 反而要
 * 额外处理缓存失效。这里只要一个本地状态机 + 顺序推进的日志。
 */

import { useCallback, useRef, useState } from 'react'

export type ActionPhase = 'idle' | 'running' | 'done' | 'failed'

export interface ActionLogLine {
  at: string
  text: string
  ok?: boolean
}

export interface StageActionState {
  phase: ActionPhase
  /** 当前进度文案（执行中显示） */
  progress: string
  /** 执行完后的一句话结果 */
  summary: string
  /** 失败原因 */
  error: string
  /** 逐步日志（执行中一行行追加，演示时最有说服力） */
  log: ActionLogLine[]
}

const INITIAL: StageActionState = { phase: 'idle', progress: '', summary: '', error: '', log: [] }

/** 把 ISO 时间截成 HH:mm:ss，日志用 */
function nowLabel(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/**
 * 跑一段带步骤的动作。
 *
 * `steps` 是「做什么」的剧本：每步一条文案 + 可选耗时。
 * 演示场景下用 setTimeout 模拟耗时（真实接口慢的时候也是这个观感），
 * 但**结果是真实的**——`run` 的返回值决定 summary。
 */
export function useStageAction<T>(options: {
  /** 每步的文案与耗时（毫秒）。耗时为 0 表示立即 */
  steps: { text: string; ms?: number }[]
  /** 真正干活的地方；抛错则进 failed */
  run?: () => Promise<T>
  /** 成功后把返回值转成一句话摘要 */
  toSummary?: (r: T) => string
}) {
  const { steps, run, toSummary } = options
  const [state, setState] = useState<StageActionState>(INITIAL)
  const alive = useRef(true)

  const reset = useCallback(() => {
    alive.current = false
    // 复位后重新允许执行
    setTimeout(() => {
      alive.current = true
    }, 0)
    setState(INITIAL)
  }, [])

  const execute = useCallback(async () => {
    setState({ ...INITIAL, phase: 'running', progress: steps[0]?.text ?? '处理中…' })
    const log: ActionLogLine[] = []

    // 逐步推进日志（即使有真接口，也让每一步都看得见）
    for (const s of steps) {
      setState((v) => ({ ...v, progress: s.text }))
      log.push({ at: nowLabel(), text: s.text })
      setState((v) => ({ ...v, log: [...log] }))
      await new Promise((r) => setTimeout(r, s.ms ?? 320))
    }

    try {
      const result = run ? await run() : undefined
      log.push({ at: nowLabel(), text: '完成', ok: true })
      setState({
        phase: 'done',
        progress: '',
        summary: toSummary && result !== undefined ? toSummary(result) : "已完成",
        error: '',
        log,
      })
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      log.push({ at: nowLabel(), text: `失败：${msg}`, ok: false })
      setState({ phase: 'failed', progress: '', summary: '', error: msg, log })
    }
  }, [steps, run, toSummary])

  return { ...state, execute, reset }
}
