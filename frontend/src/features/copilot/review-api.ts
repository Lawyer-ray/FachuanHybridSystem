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
 * - **触发**（`runReview` / `startSynthesisJob`）：花钱动作（一轮三栏评审约 5 万 token），
 *   只能在律师点了按钮之后调用。评审是一次长请求（放宽 ky 的 10s 默认超时）；综合是
 *   **后台任务**：提交后立即返回任务，再轮询到终态（`waitForSynthesisJob`）；
 * - **采纳**（`adoptReview`）：只落一条留痕（stage=shadow），不改写任何内容。
 */

import { api } from '@/lib/api'

import type { Review, Synthesis, SynthesisJob } from './adjudication-types'
import type { ReviewAdoptPayload, ReviewAdoptionEnvelope, ReviewAdoptionWire } from './domain'

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
 * 评审结算是 N×M 次 judge 调用，ky 默认 10s 必然超时；给足 3 分钟。
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

/** 综合任务的提交参数（与后端 `SynthesisIn` 一一对应） */
export interface SynthesisInput {
  turn: number
  agents: string[]
  /** 空串 = 交给所选 agent 按平台默认解析 */
  model: string
  /** 用哪个 agent 运行时做综合（后端注册表 kind）；默认 `pi` */
  kind?: string
  /** 是否先跑一轮评审再把结论喂给综合（默认 true，约 5 万 token） */
  review?: boolean
  /** 威科凭证；省略 = 服务端自动挑本所的威科账号 */
  credentialId?: number | null
}

/** 提交只做校验与入队，很快返回；30s 足够覆盖冷启动。 */
export const SYNTHESIS_SUBMIT_TIMEOUT_MS = 30_000

/** 轮询间隔。 */
export const SYNTHESIS_POLL_INTERVAL_MS = 2_000

/**
 * 前端最多等多久。后端流水线上限约 17.5 分钟（`jobs.JOB_TIMEOUT_SECONDS`），这里留余量。
 * 超过只是**停止轮询**并提示稍后再看，后端任务不受影响。
 */
export const SYNTHESIS_MAX_WAIT_MS = 20 * 60_000

/** 轮询连续失败几次后放弃（偶发网络抖动不该让一次几分钟的综合"失败"）。 */
const SYNTHESIS_POLL_MAX_ERRORS = 3

/**
 * 提交一次综合结论任务（`POST /agent/sessions/{id}/synthesize`），立即返回任务。
 *
 * 花钱动作，只能由按钮触发。同一轮已有进行中的任务时后端返回那一个（`created=false`），
 * 不会重复花钱。
 */
export function startSynthesisJob(sessionId: string, input: SynthesisInput): Promise<SynthesisJob> {
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
      timeout: SYNTHESIS_SUBMIT_TIMEOUT_MS,
    })
    .json<SynthesisJob>()
}

/** 读某个综合任务（`GET /agent/sessions/{id}/synthesis/jobs/{jobId}`）。 */
export function fetchSynthesisJob(sessionId: string, jobId: string): Promise<SynthesisJob> {
  return api.get(`agent/sessions/${sessionId}/synthesis/jobs/${jobId}`).json<SynthesisJob>()
}

/**
 * 某一轮最近一次综合任务（`GET /agent/sessions/{id}/synthesis/jobs?turn=`）。
 *
 * 刷新页面后据此接着显示进度。该轮没提交过时 404——**正常态**，调用方静默处理。
 */
export function fetchLatestSynthesisJob(sessionId: string, turn: number): Promise<SynthesisJob> {
  return api.get(`agent/sessions/${sessionId}/synthesis/jobs`, { searchParams: { turn } }).json<SynthesisJob>()
}

/**
 * 取消综合任务（`POST /agent/sessions/{id}/synthesis/jobs/{jobId}/cancel`）。
 *
 * 排队中立即变 `cancelled`；运行中只置 `cancel_requested`，后台几秒内停下（继续轮询可见）。
 */
export function cancelSynthesisJob(sessionId: string, jobId: string): Promise<SynthesisJob> {
  return api.post(`agent/sessions/${sessionId}/synthesis/jobs/${jobId}/cancel`).json<SynthesisJob>()
}

/** 任务是否还在进行中（排队 / 运行）。 */
export function isSynthesisJobActive(job: Pick<SynthesisJob, 'status'>): boolean {
  return job.status === 'queued' || job.status === 'running'
}

/** 轮询超过 {@link SYNTHESIS_MAX_WAIT_MS} 仍未结束（后端任务照常在跑）。 */
export class SynthesisWaitTimeoutError extends Error {
  constructor() {
    super('综合结论仍在后台生成，稍后回到这一轮即可查看')
    this.name = 'SynthesisWaitTimeoutError'
  }
}

function abortError(): DOMException {
  return new DOMException('已停止等待综合结论', 'AbortError')
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError())
      return
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    const onAbort = () => {
      clearTimeout(timer)
      reject(abortError())
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

/**
 * 轮询任务直到终态（`succeeded` / `failed` / `cancelled`），返回终态任务。
 *
 * - `signal` 中止 = **只停止轮询**（组件卸载 / 切轮次），不取消后端任务，reject `AbortError`；
 * - 超过 `maxWaitMs` reject {@link SynthesisWaitTimeoutError}；
 * - 单次轮询失败会重试，连续失败 3 次才放弃（reject 最后一次的错误）。
 */
export async function waitForSynthesisJob(
  sessionId: string,
  job: SynthesisJob,
  options: {
    signal?: AbortSignal
    onUpdate?: (job: SynthesisJob) => void
    intervalMs?: number
    maxWaitMs?: number
  } = {},
): Promise<SynthesisJob> {
  const { signal, onUpdate, intervalMs = SYNTHESIS_POLL_INTERVAL_MS, maxWaitMs = SYNTHESIS_MAX_WAIT_MS } = options
  const deadline = Date.now() + maxWaitMs
  let current = job
  let errors = 0
  while (isSynthesisJobActive(current)) {
    if (Date.now() >= deadline) throw new SynthesisWaitTimeoutError()
    await sleep(intervalMs, signal)
    try {
      current = await fetchSynthesisJob(sessionId, current.job_id)
      errors = 0
    } catch (error) {
      if (signal?.aborted) throw abortError()
      errors += 1
      if (errors >= SYNTHESIS_POLL_MAX_ERRORS) throw error
      continue
    }
    if (signal?.aborted) throw abortError()
    onUpdate?.(current)
  }
  return current
}

/**
 * 提交 + 轮询到终态，返回结论（便捷封装；需要进度 / 取消时直接用上面三件）。
 *
 * 任务 `failed` / `cancelled` 时 reject，错误文案取后端给的人话原因。
 */
export async function runSynthesis(
  sessionId: string,
  input: SynthesisInput,
  options: Parameters<typeof waitForSynthesisJob>[2] = {},
): Promise<Synthesis> {
  const job = await waitForSynthesisJob(sessionId, await startSynthesisJob(sessionId, input), options)
  if (job.status === 'succeeded' && job.synthesis) return job.synthesis
  if (job.status === 'cancelled') throw new Error('综合结论已取消')
  throw new Error(job.error || '综合结论生成失败，请稍后重试')
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
