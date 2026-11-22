/**
 * 一轮多答的「评审 / 综合结论」数据源与动作。
 *
 * ## 为什么必须由按钮触发
 *
 * 一轮三栏评审是 N 栏 × M 条 rubric × judge，约 5 万 token；综合结论再叠一次聚合
 * 调用。两者都**不能**随对话自动跑：律师没点就不该花钱，读答案时也不该被一张自己
 * 没要过的卡先入为主。所以这里只做三件事——读已有结果（回放）、跑用户点的那一个、
 * 把结果回填本地。
 *
 * ## 404 是正常态
 *
 * 该轮还没评审过 / 还没合成过时后端回 404：整块不渲染，不弹错、不阻塞对话。评审与
 * 综合结论都是**附加信息**，缺它们不能影响律师读答案。
 *
 * ## 为什么不进 store
 *
 * 评审是只读展示 + 单组本地状态，与转录的流式生命周期无关；放进 store 会多出一份
 * 「哪一轮的评审还在内存里」的缓存键，切会话/刷新还得手动清。
 *
 * ## 两个动作互不依赖
 *
 * 后端契约说得很清楚：`Review` 判「哪栏更好」，`Synthesis` 产「一份合成稿」，可以只跑
 * 其中一个。所以这里不把合成做成评审的后续步骤，只由 UI 决定按钮先后。
 */

import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { errMessage } from '@/lib/errors'

import { fetchReview, fetchReviewOptions, fetchSynthesis, runReview, runSynthesis, type ReviewOptions } from '../../api'
import { toReviewView, toSynthesisView, type ReviewView, type SynthesisView } from '../../domain/fusion'

/** 与后端 `rubric.DEFAULT_RUBRIC_ID` 同口径：UI 暂无评分标准选择器 */
const DEFAULT_RUBRIC_ID = 'contract_answer_v1'

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
  reviewRunning: boolean
  synthesisRunning: boolean
  startReview: () => void
  startSynthesis: () => void
  /** 综合用哪个 agent 运行时（默认 pi；可换成本轮任意一栏的 kind） */
  synthesisKind: string
  setSynthesisKind: (kind: string) => void
  /** 综合用哪个模型（空 = 交给所选 agent 按平台默认解析） */
  synthesisModel: string
  setSynthesisModel: (model: string) => void
  /** 先跑评审再综合（默认开：评审分数是综合取舍的依据） */
  synthesisWithReview: boolean
  setSynthesisWithReview: (on: boolean) => void
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
  const [reviewRunning, setReviewRunning] = useState(false)
  const [synthesisRunning, setSynthesisRunning] = useState(false)
  // 默认 pi：注册表里最稳的一个（与后端 agent_runner.DEFAULT_SYNTHESIS_KIND 同值）。
  const [synthesisKind, setSynthesisKind] = useState('pi')
  const [synthesisModel, setSynthesisModel] = useState('')
  const [synthesisWithReview, setSynthesisWithReview] = useState(true)

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

  // 回放：切换轮次/会话时先把上一轮的结果清掉，避免短暂挂出别轮的卡片（错位的证据
  // 比不显示更糟）。两个 404/网络失败都降级为「没有这张卡」。
  useEffect(() => {
    if (!sessionId || turn === null) {
      setReview(null)
      setSynthesis(null)
      return
    }
    let cancelled = false
    setReview(null)
    setSynthesis(null)
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
    return () => {
      cancelled = true
    }
  }, [sessionId, turn])

  const judgeModels = options?.judge_models ?? null

  const submitReview = async (targetSessionId: string, targetTurn: number): Promise<void> => {
    setReviewRunning(true)
    try {
      const wire = await runReview(targetSessionId, {
        turn: targetTurn,
        agents: [...agents],
        // 评分标准暂取平台给的第一把；没有清单时用契约默认值
        rubricId: options?.rubric_ids[0] || DEFAULT_RUBRIC_ID,
        // 平台清单 = judge 的模型与重试回退链；空 = 交给服务端解析
        judgeModels: judgeModels ?? [],
      })
      setReview(toReviewView(wire))
    } catch (error) {
      toast.error('评审失败', { description: errMessage(error, '请稍后重试') })
    } finally {
      setReviewRunning(false)
    }
  }

  const startReview = (): void => {
    if (!sessionId || turn === null || reviewRunning || agents.length === 0) return
    void submitReview(sessionId, turn)
  }

  const submitSynthesis = async (targetSessionId: string, targetTurn: number): Promise<void> => {
    setSynthesisRunning(true)
    try {
      const wire = await runSynthesis(targetSessionId, {
        turn: targetTurn,
        agents: [...agents],
        // 空串 = 交给所选 agent 按平台默认解析
        model: synthesisModel,
        kind: synthesisKind,
        review: synthesisWithReview,
      })
      setSynthesis(toSynthesisView(wire))
      // 综合内部会先跑评审（后端同一条链路），但它不经过本 hook 的 setReview。
      // 成功后回读一次，把打分卡补上——否则「先评审」勾了却看不到任何打分。
      if (synthesisWithReview) {
        fetchReview(targetSessionId, targetTurn)
          .then((value) => setReview(toReviewView(value)))
          .catch(() => {
            /* 评审没落库/没跑成都不影响综合结果，静默即可 */
          })
      }
    } catch (error) {
      toast.error('综合结论失败', { description: errMessage(error, '请稍后重试') })
    } finally {
      setSynthesisRunning(false)
    }
  }

  const startSynthesis = (): void => {
    if (!sessionId || turn === null || synthesisRunning || agents.length === 0) return
    void submitSynthesis(sessionId, turn)
  }

  return {
    review,
    synthesis,
    judgeModels,
    reviewRunning,
    synthesisRunning,
    startReview,
    startSynthesis,
    synthesisKind,
    setSynthesisKind,
    synthesisModel,
    setSynthesisModel,
    synthesisWithReview,
    setSynthesisWithReview,
  }
}
