import { useCallback, useEffect, useRef, useState } from 'react'

import { errMessage } from '@/lib/errors'

import {
  applyArchive,
  applyStamp,
  executeCourtFiling,
  executeOAFiling,
  getArchiveSession,
  getStampSession,
  getCourtFilingSession,
  getOAFilingSession,
  type ExecuteCourtFilingIn,
  type ExecuteOAFilingIn,
  type OAFilingSession,
  type StampSessionOut,
  type ArchiveSessionOut,
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

/** 初始态工厂。用函数而不是常量：常量 `session: null` 会让 TS 推断成
 *  `null` 类型，与 `TOut | null` 合并时退化成 `any`，调用点全变 unsafe。 */
function idleState<TOut>(): AutoRunState<TOut> {
  return { phase: 'idle', session: null, status: '', error: null, ticks: 0 }
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

/** useAutoRun 的返回值。显式声明，不靠推断 ——
 *  两个调用点（OA / 一张网）都用同一形状，推断容易在泛型边界退化成 any。 */
export interface AutoRun<TOut> {
  state: AutoRunState<TOut>
  run: (payload: unknown) => Promise<void>
  reset: () => void
}

function useAutoRun<TOut>(
  submit: (payload: unknown) => Promise<SubmitResult>,
  poll: (sessionId: number) => Promise<TOut>,
  readStatus: (s: TOut) => string,
): AutoRun<TOut> {
  const [state, setState] = useState<AutoRunState<TOut>>(idleState<TOut>)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const reset = useCallback(() => setState(idleState<TOut>()), [])

  const run = useCallback(
    async (payload: unknown) => {
      setState({ ...idleState<TOut>(), phase: 'submitting' })
      // 声明成 number | null：submit 的返回形状是 { sessionId: number | null }，
      // 下面先判 null 提前 return，赋给 number 会让 TS 拒绝这个赋值本身。
      let sessionId: number | null
      try {
        // 本 hook 对载荷内容一无所知，只负责把它交给 submit。
        // 用 unknown 而非 never：never 会让调用点的强类型一起被抹掉，
        // 传错字段也不报错。
        const r = await submit(payload)
        sessionId = r.sessionId
        if (sessionId == null) {
          // 后端没给 session：可能是同步完成，也可能直接失败。
          // 不假装成功 —— 把后端的 message 原样抛出。
          setState({ ...idleState<TOut>(), phase: 'done', status: r.status })
          return
        }
        setState((s) => ({ ...s, phase: 'running', status: r.status }))
      } catch (e) {
        if (!alive.current) return
        setState({ ...idleState<TOut>(), phase: 'done', error: errMessage(e, '任务提交失败') })
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
            setState((prev) => ({ ...prev, phase: 'done', error: errMessage(e, '任务执行失败') }))
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

/**
 * 盖章 / 归档会话的最小公共形状。
 *
 * 为什么需要它：这两个会话结构一致（id/status/error_message），但类型是两个
 * 不同的生成物。直接写 `useAutoRun<StampSessionOut | ArchiveSessionOut>` 会
 * 让调用点的条件分支无法收窄；收成结构类型后两边都能赋值。
 */
export interface OASessionLike {
  id: number
  status: string
  error_message: string
}

/**
 * OA 盖章：提交 → 轮询会话。
 *
 * 与 OA 立案的区别在**入参**：立案给 contract_id，盖章给 file_path
 * （后端按文件路径反查文件夹绑定，再由绑定找合同）。
 */
export function useOAStamp(siteName = "") {
  return useAutoRun<OASessionLike>(
    async (payload) => {
      const filePath = payload as string
      const r: StampSessionOut = await applyStamp({ file_path: filePath, site_name: siteName })
      return { sessionId: r.id ?? null, status: r.status ?? '' }
    },
    async (id): Promise<OASessionLike> => {
      const r: StampSessionOut = await getStampSession(id)
      return { id: r.id, status: r.status, error_message: r.error_message }
    },
    (s) => s.status,
  )
}

/** OA 归档：提交 → 轮询会话（可一次多个文件路径） */
export function useOAArchive(siteName = "") {
  return useAutoRun<OASessionLike>(
    async (payload) => {
      const filePaths = payload as string[]
      const r: ArchiveSessionOut = await applyArchive({ file_paths: filePaths, site_name: siteName })
      return { sessionId: r.id ?? null, status: r.status ?? '' }
    },
    async (id): Promise<OASessionLike> => {
      const r: ArchiveSessionOut = await getArchiveSession(id)
      return { id: r.id, status: r.status, error_message: r.error_message }
    },
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
