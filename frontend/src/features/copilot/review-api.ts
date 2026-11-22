/**
 * 多答评审 / 综合结论 / 采纳的 API 客户端（`/api/v1/agent` 的评审子域）。
 *
 * ## 为什么单独成文件
 *
 * `api.ts` 已到 450 行硬红线（`docs/harness/frontend/index.md`）：评审这一组端点
 * （读取 + 触发 + 采纳）自成一节，放这里按职责拆分，不再往 api.ts 里堆。
 * 调用方仍从 `./api` / `'../../api'` 引入——api.ts 原样 re-export（与 `types.ts`
 * re-export `backend-types.ts` 同口径），既有 import 路径一个都不用改。
 *
 * ## 三类请求的成本完全不同
 *
 * - **读**（`fetchReview` / `fetchReviewOptions` / `fetchSynthesis` / `fetchReviewAdoption`）：
 *   纯回放，404 一律是**正常态**（该轮没评审过/没合成过/没人采纳），调用方按
 *   「没有这张卡」处理，不弹错；
 * - **触发**（`runReview` / `runSynthesis`）：花钱动作（一轮三栏评审约 5 万 token），
 *   只能在律师点了按钮之后调用，且必须放宽 ky 的 10s 默认超时；
 * - **采纳**（`adoptReview`）：只落一条留痕（stage=shadow），不改写任何内容。
 */

import { api } from '@/lib/api'

import type { Review, Synthesis } from './adjudication-types'
import type { ReviewAdoptPayload, ReviewAdoptionEnvelope, ReviewAdoptionWire } from './domain/adoption'

/**
 * 取某一轮的评审结果（`GET /agent/sessions/{id}/review?turn=`）。
 *
 * 该轮还没评审过时后端回 404——那是**正常态**，调用方按「没有裁决卡」处理，
 * 不弹错误。`turn` 口径 = 会话里第几条 user 消息（1 起），不是消息 id；
 * 历史分页导致窗口不完整时前端算不出正确 turn，宁可不挂卡（见 domain/fusion
 * 的 `reviewTurnOf`）。
 */
export function fetchReview(sessionId: string, turn: number): Promise<Review> {
  return api.get(`agent/sessions/${sessionId}/review`, { searchParams: { turn } }).json<Review>()
}

/** `GET /agent/review/options` 的线上形状（snake_case；契约 §C1） */
export interface ReviewOptions {
  /** 可用的评分标准 id；前端暂只取第一项（无选择器） */
  rubric_ids: string[]
  /** 平台真实可用的 judge 模型清单；**空 = 平台没有可用模型**，按钮必须置灰并说明原因 */
  judge_models: string[]
  max_lanes: number
}

/**
 * 评审的可选项（`GET /agent/review/options`）。
 *
 * 为什么需要它：`judge_models` 只能来自平台真实模型清单（后端 `_available_models()`），
 * 前端**不许**自己猜模型名——猜错的表现是评审恒失败，而错误信息看起来像无权限。
 */
export function fetchReviewOptions(): Promise<ReviewOptions> {
  return api.get('agent/review/options').json<ReviewOptions>()
}

/**
 * 评审/综合结算是 N×M 次 judge 调用，ky 默认 10s 必然超时；给足 3 分钟。
 *
 * 不做自动重试：一次评审的钱是按 token 算的，失败后由律师自己再点。
 */
export const REVIEW_TIMEOUT_MS = 180_000

/**
 * 触发一轮评审（`POST /agent/sessions/{id}/review`，独立请求、不进 SSE）。
 *
 * `judgeModels` 传平台清单（空数组 = 请服务端按配置/本轮栏模型解析，契约 §C2）。
 * 注意这是**花钱动作**：一轮三栏评审约 5 万 token，只能在律师点了按钮之后调用。
 */
export function runReview(
  sessionId: string,
  input: { turn: number; agents: string[]; rubricId: string; judgeModels: string[] },
): Promise<Review> {
  return api
    .post(`agent/sessions/${sessionId}/review`, {
      json: {
        turn: input.turn,
        agents: input.agents,
        rubric_id: input.rubricId,
        judge_models: input.judgeModels,
      },
      timeout: REVIEW_TIMEOUT_MS,
    })
    .json<Review>()
}

/**
 * 读某一轮已落库的综合结论（`GET /agent/sessions/{id}/synthesis?turn=`）。
 *
 * 该轮没跑过时后端回 404——那是**正常态**，调用方按「没有综合结论卡」处理，
 * 不弹错误（与 `fetchReview` 同口径）。
 */
export function fetchSynthesis(sessionId: string, turn: number): Promise<Synthesis> {
  return api.get(`agent/sessions/${sessionId}/synthesis`, { searchParams: { turn } }).json<Synthesis>()
}

/**
 * 跑一次综合结论（`POST /agent/sessions/{id}/synthesize`）。
 *
 * `model` 空 = 服务端按本轮各栏模型解析（契约 §C4）——**不用**评审模型配置：
 * 合成看的是候选的模型，不是 judge。同样是花钱动作，只能由按钮触发。
 */
export function runSynthesis(
  sessionId: string,
  input: {
    turn: number
    agents: string[]
    model: string
    /** 用哪个 agent 运行时做综合（后端注册表 kind）；默认 `pi` */
    kind?: string
    /** 是否先跑一轮评审再把结论喂给综合（默认 true，约 5 万 token） */
    review?: boolean
    /** 威科凭证：给了才做外部引用核验 */
    credentialId?: number | null
  },
): Promise<Synthesis> {
  return api
    .post(`agent/sessions/${sessionId}/synthesize`, {
      json: {
        turn: input.turn,
        agents: input.agents,
        model: input.model,
        kind: input.kind ?? 'pi',
        review: input.review ?? true,
        credential_id: input.credentialId ?? null,
      },
      timeout: REVIEW_TIMEOUT_MS,
    })
    .json<Synthesis>()
}

/**
 * 提交采纳 / 标为合并 / 理由（`POST /agent/reviews/{id}/adopt`）。
 *
 * 只落一条决定，不改写任何内容（stage=shadow）。`lane=null + merged=true` 表示
 * 合并采纳；返回落库后的采纳记录。刷新后的回显走 {@link fetchReviewAdoption}，
 * 不要在这里另存一份缓存。
 */
export function adoptReview(reviewId: string, payload: ReviewAdoptPayload): Promise<ReviewAdoptionWire> {
  return api.post(`agent/reviews/${reviewId}/adopt`, { json: payload }).json<ReviewAdoptionWire>()
}

/**
 * 读采纳记录（`GET /agent/reviews/{id}/adoption`）。
 *
 * `adoption: null` 与 404 同义（还没人采纳）：调用方一律按「没有采纳记录」展示。
 */
export function fetchReviewAdoption(reviewId: string): Promise<ReviewAdoptionEnvelope> {
  return api.get(`agent/reviews/${reviewId}/adoption`).json<ReviewAdoptionEnvelope>()
}
