/**
 * 一轮多答的「评审卡 / 综合结论」数据源与动作。
 *
 * ## 只有一个花钱的动作：生成综合结论
 *
 * 评审是综合的第一步（「先评审」默认勾选，后端在同一个任务里跑完并落库），不再有独立的
 * 评审按钮。评审卡只做回放：该轮评审过就挂出来，综合成功且这次先评审了就回读一次。
 *
 * 两者都**不能**随对话自动跑：律师没点就不该花钱，读答案时也不该被一张自己没要过的卡
 * 先入为主。
 *
 * ## 综合是后台任务
 *
 * 一次综合（评审 + agent 综合 + 威科核验）常常跑几分钟。点按钮 = 提交任务，立即返回；
 * 之后轮询到终态（`waitForSynthesisJob`），期间显示阶段、可以取消。
 *
 * - **组件卸载 / 切轮次只停止轮询，不取消后台任务**：结果会落库，回到这一轮能看到；
 * - **刷新页面接着显示进度**：挂载时查该轮最近一次任务，还在跑就接着轮询；
 * - 重复点击由后端去重（同一轮只有一个进行中的任务），这里拿到的就是已在跑的那个。
 *
 * ## 404 是正常态
 *
 * 该轮还没评审过 / 还没合成过 / 没提交过任务时后端回 404：整块不渲染，不弹错、不阻塞
 * 对话。评审与综合结论都是**附加信息**，缺它们不能影响律师读答案。
 *
 * ## 为什么不进 store
 *
 * 评审是只读展示 + 单组本地状态，与转录的流式生命周期无关；放进 store 会多出一份
 * 「哪一轮的评审还在内存里」的缓存键，切会话/刷新还得手动清。
 */

import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { errMessage } from '@/lib/errors'

import { fetchReview, fetchReviewOptions, fetchSynthesis, type ReviewOptions } from '../../api'
import type { SynthesisJob } from '../../adjudication-types'
import type { AgentBackendOption } from '../../backend-types'
import { agentLabel } from '../../domain'
import { useCopilot } from '../../store'
import { findBackend } from '../../store/backends'
import { toReviewView, toSynthesisView, type ReviewView, type SynthesisView } from '../../domain/fusion'
import {
  cancelSynthesisJob,
  fetchLatestSynthesisJob,
  isSynthesisJobActive,
  startSynthesisJob,
  SynthesisWaitTimeoutError,
  waitForSynthesisJob,
} from '../../review-api'

export interface ReviewActions {
  review: ReviewView | null
  synthesis: SynthesisView | null
  /**
   * 平台可用的 judge 模型清单。
   *
   * `null` = 还没取到（或取失败）：不据此禁用按钮——契约 §C2 允许 `judge_models` 为空、
   * 由服务端按配置/本轮栏模型解析。只有**明确拿到空清单**才说明平台没有可用模型。
   */
  judgeModels: string[] | null
  /** 正在提交或后台任务进行中（按钮置灰、显示进度） */
  synthesisRunning: boolean
  /** 正在提交（还没拿到任务） */
  synthesisSubmitting: boolean
  /** 当前跟踪的后台任务（进行中或刚结束）；`null` = 没有 */
  synthesisJob: SynthesisJob | null
  /** 已请求取消、等待后台停下 */
  synthesisCancelling: boolean
  startSynthesis: () => void
  cancelSynthesis: () => void
  /** 综合用哪个 agent 运行时（默认 pi；可换成本轮任意一栏的 kind） */
  synthesisKind: string
  setSynthesisKind: (kind: string) => void
  /**
   * 下拉框当前显示的模型（空串 = 「自动」：后端取本轮某栏实际用过的模型，取不到再交给
   * 所选 agent 按平台默认解析，见 `services/synthesis/pipeline`）。
   * 律师还没选过时显示当前执行 agent 清单的第一项，提交的也是它。
   */
  synthesisModel: string
  setSynthesisModel: (model: string) => void
  /** 当前执行 agent 可选的模型（`null` = 还不知道）；见 {@link synthesisModelsFor} */
  synthesisModels: string[] | null
  /** 当前执行 agent 跑不了综合的原因（没有可用模型）；空串 = 可以跑 */
  synthesisBlockedReason: string
  /** 先跑评审再综合（默认开：评审分数是综合取舍的依据） */
  synthesisWithReview: boolean
  setSynthesisWithReview: (on: boolean) => void
}

/** 后端清单缺省（模块级常量：保持引用稳定） */
const NO_BACKENDS: AgentBackendOption[] = []

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

/**
 * 用 `kind` 跑综合时可选的模型。
 *
 * 唯一口径是后端 `GET /agent/backends` 的 `models`：服务端已按运行时收窄（claude-agent
 * 只留 Anthropic 协议模型，见 `session_api._models_for_kind`），前端不再写任何模型名规则。
 * 后端清单还没拉到、或清单里没有这个 kind（旧部署没有 `models` 字段）时，退回平台清单
 * `platformModels`（`/review/options` 的 `judge_models`，与 backends 同一来源）。
 *
 * @returns `null` = 两份清单都还不知道；`[]` = 明确没有可用模型。
 */
export function synthesisModelsFor(
  backends: AgentBackendOption[],
  kind: string,
  platformModels: string[] | null,
): string[] | null {
  const models = findBackend(backends, kind)?.models
  return models ?? platformModels
}

/**
 * @param sessionId 会话（null = 还没有会话，不读不跑）
 * @param turn 会话内第几轮（1 起）；`null` = 算不出轮次（历史窗口不完整），见 `reviewTurnOf`
 * @param agents 本轮的栏（`agent_kind`，顺序 = 请求顺序）。调用方必须传稳定引用
 */
export function useReviewActions(
  sessionId: string | null,
  turn: number | null,
  agents: readonly string[],
): ReviewActions {
  const [review, setReview] = useState<ReviewView | null>(null)
  const [synthesis, setSynthesis] = useState<SynthesisView | null>(null)
  const [options, setOptions] = useState<ReviewOptions | null>(null)
  const [job, setJob] = useState<SynthesisJob | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [cancelRequesting, setCancelRequesting] = useState(false)
  // 默认 pi：注册表里最稳的一个（与后端 agent_runner.DEFAULT_SYNTHESIS_KIND 同值）。
  const [synthesisKind, setSynthesisKind] = useState('pi')
  // 律师在模型下拉里的**明确选择**：`null` = 还没选过（显示并提交清单第一项）；
  // `''` = 明确选了「自动」（提交空串，由后端解析）；其余为具体模型名。
  // 「还没选」与「选了自动」必须分开：v27.22.7 用 `synthesisModel || 第一项` 兜「清单到达前
  // 就点了按钮」，结果把律师主动选的「自动」也改成了第一项。
  const [modelChoice, setModelChoice] = useState<string | null>(null)
  const [synthesisWithReview, setSynthesisWithReview] = useState(true)
  // 当前轮询的中止器：卸载 / 切轮次时 abort（只停轮询，不取消后台任务）。
  const pollRef = useRef<AbortController | null>(null)
  // 当前展示的是哪一轮：提交请求回来时轮次已经切走，就不能把任务挂到新一轮上。
  const targetRef = useRef<{ sessionId: string | null; turn: number | null }>({ sessionId, turn })

  // 选项是平台级配置（不是某一轮的数据）：只在挂载时取一次。
  // 取失败不拦功能：judge_models 允许为空，服务端会按配置解析。
  useEffect(() => {
    let cancelled = false
    fetchReviewOptions()
      .then((value) => {
        if (!cancelled) setOptions(value)
      })
      .catch(() => {
        if (!cancelled) setOptions(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  /** 任务结束：成功挂结论（并回读评审卡），失败 / 取消给一句提示。 */
  const settle = (targetSessionId: string, targetTurn: number, finished: SynthesisJob): void => {
    if (finished.status === 'succeeded') {
      if (finished.synthesis) setSynthesis(toSynthesisView(finished.synthesis))
      // 评审在同一个后台任务里跑完并落库，但不经过这里的 setReview：回读一次把打分卡补上。
      if (finished.review) {
        fetchReview(targetSessionId, targetTurn)
          .then((value) => setReview(toReviewView(value)))
          .catch(() => {
            /* 评审没落库/没跑成都不影响综合结果，静默即可 */
          })
      }
    } else if (finished.status === 'failed') {
      toast.error('综合结论失败', { description: finished.error || '请稍后重试' })
    } else if (finished.status === 'cancelled') {
      toast('已取消综合结论')
    }
  }

  /** 轮询一个进行中的任务到终态（替换掉之前的轮询）。 */
  const track = async (targetSessionId: string, targetTurn: number, initial: SynthesisJob): Promise<void> => {
    pollRef.current?.abort()
    const controller = new AbortController()
    pollRef.current = controller
    setJob(initial)
    try {
      const finished = await waitForSynthesisJob(targetSessionId, initial, {
        signal: controller.signal,
        onUpdate: setJob,
      })
      if (controller.signal.aborted) return
      setJob(finished)
      settle(targetSessionId, targetTurn, finished)
    } catch (error) {
      if (controller.signal.aborted || isAbortError(error)) return
      // 停止跟踪（按钮恢复可点）：后台任务照常在跑，再点一次会拿到同一个任务接着看。
      setJob(null)
      if (error instanceof SynthesisWaitTimeoutError) toast(error.message)
      else toast.error('读取综合进度失败', { description: errMessage(error, '稍后回到这一轮即可查看') })
    } finally {
      if (pollRef.current === controller) pollRef.current = null
    }
  }

  // 回放：切换轮次/会话时先把上一轮的结果清掉，避免短暂挂出别轮的卡片（错位的证据
  // 比不显示更糟）。404/网络失败都降级为「没有这张卡」。该轮有进行中的任务就接着轮询。
  useEffect(() => {
    targetRef.current = { sessionId, turn }
    pollRef.current?.abort()
    pollRef.current = null
    setReview(null)
    setSynthesis(null)
    setJob(null)
    setSubmitting(false)
    setCancelRequesting(false)
    if (!sessionId || turn === null) return
    let cancelled = false
    fetchReview(sessionId, turn)
      .then((wire) => {
        if (!cancelled) setReview(toReviewView(wire))
      })
      .catch(() => {
        if (!cancelled) setReview(null)
      })
    fetchSynthesis(sessionId, turn)
      .then((wire) => {
        if (!cancelled) setSynthesis(toSynthesisView(wire))
      })
      .catch(() => {
        if (!cancelled) setSynthesis(null)
      })
    fetchLatestSynthesisJob(sessionId, turn)
      .then((latest) => {
        if (!cancelled && isSynthesisJobActive(latest)) void track(sessionId, turn, latest)
      })
      .catch(() => {
        /* 404 = 该轮没提交过任务（正常态） */
      })
    return () => {
      cancelled = true
      pollRef.current?.abort()
      pollRef.current = null
    }
    // track / settle 只读 setState 与 ref，每轮重建无副作用；依赖只看轮次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, turn])

  const judgeModels = options?.judge_models ?? null
  // `?? NO_BACKENDS`：部分 DOM 测试整块 mock 了 store，假状态里没有这个字段
  const backends = useCopilot((s) => s.backends) ?? NO_BACKENDS
  const synthesisModels = synthesisModelsFor(backends, synthesisKind, judgeModels)
  const synthesisBlockedReason =
    synthesisModels !== null && synthesisModels.length === 0
      ? `当前 AI 平台没有「${agentLabel(synthesisKind)}」可用的模型，请换一个执行 agent`
      : ''

  // 还没选过时默认一个**具体模型**（当前执行 agent 清单的第一项，不是猜的模型名）：
  // 下拉框显示什么、提交就发什么。清单为空时才是「自动」。
  const firstModel = synthesisModels?.[0] ?? ''
  const synthesisModel = modelChoice ?? firstModel

  // 换执行 agent 后，原来明确选的模型它不一定能用（例：pi 上选的 glm53，换成 claude-agent）：
  // 切到该 agent 的第一个可用模型；它一个都没有就回到「自动」（按钮另行禁用）。
  // 没选过（null）不用管——显示值本来就跟着新清单的第一项；明确选的「自动」（空串）也不动。
  const modelsKey = synthesisModels?.join('\n') ?? null
  useEffect(() => {
    if (synthesisModels === null) return
    setModelChoice((current) =>
      current === null || current === '' || synthesisModels.includes(current) ? current : (synthesisModels[0] ?? ''),
    )
    // 依赖用清单内容而不是数组引用：每次渲染 synthesisModelsFor 都可能给出新数组
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelsKey])

  const synthesisRunning = submitting || (job !== null && isSynthesisJobActive(job))

  const submitSynthesis = async (targetSessionId: string, targetTurn: number): Promise<void> => {
    setSubmitting(true)
    let submitted: SynthesisJob
    try {
      submitted = await startSynthesisJob(targetSessionId, {
        turn: targetTurn,
        agents: [...agents],
        // 与下拉框显示一致：没选过 = 清单第一项；明确选了「自动」= 空串（后端解析）。
        model: synthesisModel,
        kind: synthesisKind,
        review: synthesisWithReview,
      })
    } catch (error) {
      toast.error('综合结论失败', { description: errMessage(error, '请稍后重试') })
      return
    } finally {
      setSubmitting(false)
    }
    const target = targetRef.current
    if (target.sessionId !== targetSessionId || target.turn !== targetTurn) return
    if (!submitted.created && isSynthesisJobActive(submitted)) {
      toast('这一轮的综合结论已在生成，继续显示它的进度')
    }
    if (isSynthesisJobActive(submitted)) {
      void track(targetSessionId, targetTurn, submitted)
    } else {
      // 例：入队失败时任务直接是 failed
      setJob(submitted)
      settle(targetSessionId, targetTurn, submitted)
    }
  }

  const startSynthesis = (): void => {
    if (!sessionId || turn === null || synthesisRunning || agents.length === 0 || synthesisBlockedReason) return
    void submitSynthesis(sessionId, turn)
  }

  const cancelSynthesis = (): void => {
    if (!sessionId || !job || !isSynthesisJobActive(job) || cancelRequesting || job.cancel_requested) return
    setCancelRequesting(true)
    cancelSynthesisJob(sessionId, job.job_id)
      // 终态由轮询收口（含「已取消」提示），这里只回显 cancel_requested / cancelled
      .then((next) => setJob((current) => (current && current.job_id === next.job_id ? next : current)))
      .catch((error: unknown) => toast.error('取消失败', { description: errMessage(error, '请稍后重试') }))
      .finally(() => setCancelRequesting(false))
  }

  return {
    review,
    synthesis,
    judgeModels,
    synthesisRunning,
    synthesisSubmitting: submitting,
    synthesisJob: job,
    synthesisCancelling: cancelRequesting || Boolean(job?.cancel_requested && isSynthesisJobActive(job)),
    startSynthesis,
    cancelSynthesis,
    synthesisKind,
    setSynthesisKind,
    synthesisModel,
    setSynthesisModel: setModelChoice,
    synthesisModels,
    synthesisBlockedReason,
    synthesisWithReview,
    setSynthesisWithReview,
  }
}
