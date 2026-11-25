/**
 * 回传件内容核对的后端对接（挂载前缀 `/api/v1/doc-verify`，见后端
 * `apps/doc_verify/api/`）。
 *
 * 四个端点：案件策略读写、待裁决清单、裁决留痕。
 *
 * 措辞提醒（会直接影响律师看到的判断）：「核对」= 客户回传件与出站基线比正文；
 * 「待裁决」= 检出问题/无法核对、还没被 accept/reject 处置的那些件。
 *
 * 类型全部取自 openapi 生成物（`src/types/api-schema.d.ts`，重生成流程见
 * `src/types/README.md`），不在这里手抄字段：手抄的形状与后端漂移时编译期
 * 发现不了，只有线上 500 能发现。
 *
 * 错误一律往外抛，由调用方用 `@/lib/errors` 的 `errMessage` 取可读文案后 toast——
 * api 层吞异常会让「点了没反应」重新变成排查黑洞。
 */
import { createApiClient } from '@/lib/api'
import type { components } from '@/types/api-schema'

export type DecisionIn = components['schemas']['DecisionIn']
export type DecisionOut = components['schemas']['DecisionOut']
export type FindingOut = components['schemas']['FindingOut']
export type PolicyIn = components['schemas']['PolicyIn']
export type PolicyItemOut = components['schemas']['PolicyItemOut']
export type PolicyOut = components['schemas']['PolicyOut']
export type VerifyRunOut = components['schemas']['VerifyRunOut']

/** 后端只认这三个值（`services/verify/decision.py` 的 DECISION_ACTIONS）。 */
export type DecisionAction = 'accept' | 'reject' | 'reissue'

const docVerifyApi = createApiClient({ prefix: '/api/v1/doc-verify' })

/** 该案每类高风险文书的实际策略（库里没有记录就取代码默认）。 */
export async function getPolicy(caseId: number, signal?: AbortSignal): Promise<PolicyOut> {
  return docVerifyApi.get('policy', { searchParams: { case_id: caseId }, signal }).json<PolicyOut>()
}

/** 批量改策略，返回改后的全量；`doc_types` 不传 = 改全部高风险类。 */
export async function putPolicy(input: PolicyIn): Promise<PolicyOut> {
  return docVerifyApi.put('policy', { json: input }).json<PolicyOut>()
}

/** 该案待裁决清单（要核对 + 检出问题 + 还没有 accept/reject 裁决）。 */
export async function listUnverified(caseId: number, signal?: AbortSignal): Promise<VerifyRunOut[]> {
  return docVerifyApi
    .get('unverified', { searchParams: { case_id: caseId }, signal })
    .json<VerifyRunOut[]>()
}

/** 跨案件的待裁决清单（材料准备页的全局入口用；后端按可见性收窄）。 */
export async function listPending(limit = 50, signal?: AbortSignal): Promise<VerifyRunOut[]> {
  return docVerifyApi
    .get('pending', { searchParams: { limit }, signal })
    .json<VerifyRunOut[]>()
}

/** 记录一条裁决（append-only）；accept/reject 之后该件即从待裁决清单消失。 */
export async function decideRun(runId: number, decision: DecisionIn): Promise<DecisionOut> {
  return docVerifyApi.post(`runs/${runId}/decision`, { json: decision }).json<DecisionOut>()
}
