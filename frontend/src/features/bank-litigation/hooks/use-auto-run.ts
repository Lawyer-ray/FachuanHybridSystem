import { useCallback, useEffect, useRef, useState } from 'react'

import { errMessage } from '@/lib/errors'

import {
  executeCourtFiling,
  executeOAFiling,
  getCourtFilingSession,
  getOAFilingSession,
  type ExecuteCourtFilingIn,
  type ExecuteOAFilingIn,
  type OAFilingSession,
} from '../api'

/** 轮询节奏：2s 一拍，与 court-sms / doc-converter 一致 */
const POLL_MS = 2000
/** 轮询上限：浏览器自动化要开页面、填表单、传附件，给到 15 分钟 */
const MAX_POLLS = 450
/** 连续查询失败宽限：偶发网络抖动不当场判死 */
const MAX_QUERY_ERRORS = 10

/**
 * 自动化任务的阶段。
 *
 * ⚠️ `running` 与 `done` 之间**没有**「成功」这个中间态：
 * OA / 一张网都是后台线程跑 Playwright，只能拿到 session 的 `status` 字符串
 * （后端写的是 pending / running / success / failed 之类）。前端不猜语义，
 * 原样展示 `status`，只把**终态**归一成 done。
 */
export type AutoPhase = 'idle' | 'submitting' | 'running' | 'done' | 'timeout'

export interface AutoRunState<TOut> {
  phase: AutoPhase
  /** 最近一次会话快照（后端原样返回，前端不改造语义） */
  session: TOut | null
  /** 会话状态字符串（pending / running / success / failed …） */
  status: string
  /** 提交动作本身的失败（连会话都没建出来） */
  error: string | null
  /** 轮询次数（给用户一个「还在跑」的进度感） */
  ticks: number
}

const IDLE = {
  phase: 'idle' as AutoPhase,
  session: null,
  status: '',
  error: null,
  ticks: 0,
}

/** 判定会话是否已到终态。后端 status 大小写不统一，统一小写比。 */
function isTerminal(status: string): boolean {
  const s = (status || '').toLowerCase()
  return s === 'success' || s === 'failed' || s === 'finished' || s === 'completed' || s === 'error'
}

/**
 * 通用「提交 → 轮询」状态机。
 *
 * 为什么两个域（OA / 一张网）共用一个 hook 而不是各写一份：
 * 它们的流程形状完全一样（POST 拿 session_id → GET 轮询 → 终态停），
 * 差别只在调哪个函数。复制两份的代价是修轮询节奏时要改两处，
 * 而这类代码最容易忘记的就是「另一份也超时了」。
 */
/** submit 的归一化回包：不同后端的字段名不同（id vs session_id），在这里收成两个字段 */
interface SubmitResult {
  sessionId: number | null
  status: string
}

function useAutoRun<TOut>(
  submit: (payload: unknown) => Promise<SubmitResult>,
  poll: (sessionId: number) => Promise<TOut>,
  readStatus: (s: TOut) => string,
) {
  const [state, setState] = useState<AutoRunState<TOut>>(IDLE)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const reset = useCallback(() => setState(IDLE), [])

  const run = useCallback(
    async (payload: unknown) => {
      setState({ ...IDLE, phase: 'submitting' })
      let sessionId: number
      try {
        // 本 hook 对载荷内容一无所知，只负责把它交给 submit。
        // 用 unknown 而非 never：never 会让调用点的强类型一起被抹掉，
        // 传错字段也不报错。
        const r = await submit(payload)
        sessionId = r.sessionId
        if (sessionId == null) {
          // 后端没给 session：可能是同步完成，也可能直接失败。
          // 不假装成功 —— 把后端的 message 原样抛出。
          setState({ ...IDLE, phase: 'done', status: r.status })
          return
        }
        setState((s) => ({ ...s, phase: 'running', status: r.status }))
      } catch (e) {
        if (!alive.current) return
        setState({ ...IDLE, phase: 'done', error: errMessage(e) })
        return
      }

      let errors = 0
      for (let i = 0; i < MAX_POLLS; i++) {
        await new Promise((r) => setTimeout(r, POLL_MS))
        if (!alive.current) return
        try {
          const s = await poll(sessionId)
          const status = readStatus(s)
          if (!alive.current) return
          errors = 0
          setState((prev) => ({ ...prev, session: s, status, ticks: i + 1 }))
          if (isTerminal(status)) {
            setState((prev) => ({ ...prev, phase: 'done' }))
            return
          }
        } catch (e) {
          errors += 1
          // 连续失败超过宽限才算失败；偶发抖动继续轮询
          if (errors >= MAX_QUERY_ERRORS) {
            if (!alive.current) return
            setState((prev) => ({ ...prev, phase: 'done', error: errMessage(e) }))
            return
          }
        }
      }
      if (!alive.current) return
      setState((prev) => ({ ...prev, phase: 'timeout' }))
    },
    [submit, poll, readStatus],
  )

  return { state, run, reset }
}

/** 律所 OA 立案：提交 → 轮询会话 */
export function useOAFiling() {
  return useAutoRun<OAFilingSession>(
    async (payload) => {
      const r = await executeOAFiling(payload as ExecuteOAFilingIn)
      // SessionOut 的真实字段是 id/status/error_message/created_at
      return { sessionId: r.id ?? null, status: r.status ?? '' }
    },
    (id) => getOAFilingSession(id),
    (s) => s.status,
  )
}

/** 一张网在线立案：提交 → 轮询会话 */
export function useCourtFiling() {
  return useAutoRun<ExecuteCourtFilingOutLike>(
    async (payload) => {
      const r = await executeCourtFiling(payload as ExecuteCourtFilingIn)
      return {
        sessionId: r.session_id ?? null,
        status: r.status ?? (r.success ? 'success' : 'failed'),
      }
    },
    (id) => getCourtFilingSession(id),
    (s) => s.status ?? (s.success ? 'success' : 'failed'),
  )
}

/** getCourtFilingSession 与 executeCourtFiling 返回同形（ExecuteCourtFilingOut） */
type ExecuteCourtFilingOutLike = Awaited<ReturnType<typeof getCourtFilingSession>>
