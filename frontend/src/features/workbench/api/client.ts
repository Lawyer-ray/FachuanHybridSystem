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
/**
 * 合同文件夹端点（`/api/v1/contracts/{id}/folder-entries|folder-file|…`）。
 *
 * 与 `contractsApi` 同为 `/api/v1/contracts` 前缀，但**路径少一段**：folder 侧
 * 的 router 写的是 `/{contract_id}/…`，CRUD 侧写的是 `/contracts/{id}`；
 * 于是 CRUD 的完整地址是 `/contracts/contracts/{id}`，folder 的是
 * `/contracts/{id}/folder-entries`。两个客户端分开建，避免拼错段数。
 */
export const contractFolderApi = createApiClient({ prefix: '/api/v1/contracts' })
export const casesApi = createApiClient({ prefix: '/api/v1/cases' })
export const organizationApi = createApiClient({ prefix: '/api/v1/organization' })
export const remindersApi = createApiClient({ prefix: '/api/v1/reminders' })
/**
 * 客户档案（`/api/v1/client/clients`：模板建项目时先落委托人与对方当事人）。
 *
 * 注意前缀是**单数** `client`、路径段是复数 `clients`——后端 router 就是这么挂的，
 * 不是笔误。
 */
export const clientApi = createApiClient({ prefix: '/api/v1/client' })
/** 材料收件箱（`/api/v1/inbox/messages/upload`：示例材料与真实上传同一条入口） */
export const inboxApi = createApiClient({ prefix: '/api/v1/inbox' })
