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
export type RunPageOut = components['schemas']['RunPageOut']
export type RunFromMaterialIn = components['schemas']['RunFromMaterialIn']
export type DecisionBatchIn = components['schemas']['DecisionBatchIn']
export type DecisionBatchOut = components['schemas']['DecisionBatchOut']

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

/** 该案的**全量**核对历史（可带 state 过滤、分页）。案件详情页用它回看「核过几次、结论怎么变」。 */
export async function listCaseRuns(
  params: { case_id: number; state?: string; limit?: number; offset?: number },
  signal?: AbortSignal,
): Promise<RunPageOut> {
  return docVerifyApi
    .get('runs', {
      searchParams: {
        case_id: params.case_id,
        ...(params.state ? { state: params.state } : {}),
        limit: params.limit ?? 50,
        offset: params.offset ?? 0,
      },
      signal,
    })
    .json<RunPageOut>()
}

/**
 * 一条回传件直接核（服务端按收件箱附件取字节）。
 *
 * 为什么不用 `/runs` + base64：整本扫描件几十上百页，前端 base64 一遍就是几十 MB 的
 * 请求体，先卡浏览器再卡网关；这一条把取字节留在服务端。
 */
export async function runFromMaterial(input: RunFromMaterialIn): Promise<VerifyRunOut> {
  return docVerifyApi.post('runs/from-material', { json: input }).json<VerifyRunOut>()
}

/** 批量裁决：逐条跳过已裁决/不可见的，返回 decided/skipped 明细。 */
export async function decideBatch(input: DecisionBatchIn): Promise<DecisionBatchOut> {
  return docVerifyApi.post('decisions/batch', { json: input }).json<DecisionBatchOut>()
}

/** 记录一条裁决（append-only）；accept/reject 之后该件即从待裁决清单消失。 */
export async function decideRun(runId: number, decision: DecisionIn): Promise<DecisionOut> {
  return docVerifyApi.post(`runs/${runId}/decision`, { json: decision }).json<DecisionOut>()
}
