import { createApiClient } from '@/lib/api'

/**
 * 办案主页数据源共用的 HTTP 客户端（按后端 router 挂载前缀各建一个）。
 *
 * 合同 + 律师列表接口只读拉取（slim 模式剔除归档材料清单，约减 60% 响应体积）；
 * 案件按合同 ID 按需加载。均返回裸数组、无业务 success 包装（见 types.ts 头注释的契约说明）。
 *
 * 拆到 `api/client.ts` 的原因：`api/` 目录下 contract / folder / invoice 三个资源
 * 文件共用同一批客户端实例（folder 的 `folderApi(kind)` 就是在 cases / contracts
 * 之间选一个），各文件自建会多出重复实例。
 */
export const contractsApi = createApiClient({ prefix: '/api/v1/contracts' })
export const casesApi = createApiClient({ prefix: '/api/v1/cases' })
export const organizationApi = createApiClient({ prefix: '/api/v1/organization' })
export const remindersApi = createApiClient({ prefix: '/api/v1/reminders' })
