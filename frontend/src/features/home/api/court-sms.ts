import { automationApi } from './tools'
import { API_BASE_URL, withAuthToken } from './download'
import type { components } from '@/types/api-schema'

/**
 * 法院短信处理链路 API（对接后端 apps/automation，路径已按 OpenAPI 核对）：
 *   - 提交     = POST /automation/court-sms                    （返回 { data: { id, status } }）
 *   - 详情     = GET  /automation/court-sms/{id}               （CourtSMSDetailOut，含案件/文书引用）
 *   - 人工分配 = POST /automation/court-sms/{id}/assign-case   （匹配不到案件时手动指定，随后继续处理）
 *   - 重新处理 = POST /automation/court-sms/{id}/retry         （保留手动绑定案件，仅重跑后续流程）
 *   - 单件下载 = GET /automation/court-sms/{id}/documents/{ref_index}/download
 *   - 打包下载 = GET /automation/court-sms/{id}/documents/download-all
 */

/**
 * GET court-sms/{id} 的响应（基于生成物 CourtSMSDetailOut 的消费投影）：
 * · Omit 掉时间戳与 feishu 字段（弹窗不用）；
 * · case / documents / download_links / case_numbers / party_names 生成物声明为
 *   「可选 + 裸 dict」（schema 未覆盖），此处按真实结构手写收紧，业务当必用。
 */
export type CourtSmsDetail = Omit<
  components['schemas']['CourtSMSDetailOut'],
  'received_at' | 'created_at' | 'updated_at' | 'case' | 'documents' | 'download_links' | 'case_numbers' | 'party_names'
> & {
  download_links: string[]
  case_numbers: string[]
  party_names: string[]
  case: { id: number; name: string } | null
  documents: { id: number | null; name: string; source: string; download_url: string | null }[]
}

/** 单件文书下载地址（带下载票据，供 <a download> 直链使用；文件名后端已重命名） */
export async function courtSmsDocDownloadUrl(smsId: number, refIndex: number): Promise<string> {
  return withAuthToken(`${API_BASE_URL}/automation/court-sms/${smsId}/documents/${refIndex}/download`)
}

/** 全部文书打包 ZIP 下载地址 */
export async function courtSmsDownloadAllUrl(smsId: number): Promise<string> {
  return withAuthToken(`${API_BASE_URL}/automation/court-sms/${smsId}/documents/download-all`)
}

/**
 * 复制文书到**系统**剪贴板（后端 NSPasteboard 写 file-url，同 Finder ⌘C）。
 * 微信等应用可直接 ⌘V 粘出文件本体；后端非 macOS 时返回 reason=unsupported，
 * 调用方降级浏览器剪贴板路径。
 */
export async function copyCourtSmsDocsToClipboard(
  smsId: number,
  indexes: number[],
): Promise<{ success: boolean; copied: number; reason: string | null }> {
  // message 为 schema 未声明的业务失败文案字段，交联补充
  const res = await automationApi
    .post(`court-sms/${smsId}/documents/copy-to-clipboard`, { json: { indexes } })
    .json<components['schemas']['CourtSMSCopyDocsOut'] & { message?: string }>()
  if (res.success === undefined && res.message) throw new Error(res.message)
  return { success: res.success === true, copied: Number(res.copied ?? 0), reason: res.reason ?? null }
}

/** 查询处理详情（轮询用；404 等由调用方 catch） */
export async function getCourtSmsDetail(smsId: number): Promise<CourtSmsDetail> {
  return automationApi.get(`court-sms/${smsId}`).json<CourtSmsDetail>()
}

/** 列表行（GET court-sms 的行，生成物 CourtSMSListOut，content 已截 100 字） */
export type CourtSmsListItem = components['schemas']['CourtSMSListOut']

/** 历史筛选组：needs_action = 待人工/失败/下载失败（点开即可处理），completed = 已完成 */
export type CourtSmsGroup = 'all' | 'needs_action' | 'completed'

/** 分页查询短信列表（历史弹窗用，page_size 后端固定 20；响应为生成物 PagedCourtSMSListOut） */
export async function listCourtSms(
  group: CourtSmsGroup,
  page: number,
): Promise<{ items: CourtSmsListItem[]; count: number }> {
  const res = await automationApi
    .get('court-sms', {
      searchParams: {
        ...(group === 'all' ? {} : { status_group: group }),
        page: String(page),
      },
    })
    .json<components['schemas']['PagedCourtSMSListOut']>()
  return { items: res.items ?? [], count: res.count ?? 0 }
}

/** 人工指定案件：成功后状态进入 renaming/notifying，需要继续轮询到终态 */
export async function assignCourtSmsCase(smsId: number, caseId: number): Promise<void> {
  const res = await automationApi
    .post(`court-sms/${smsId}/assign-case`, { json: { case_id: caseId } })
    .json<{ success?: boolean; message?: string }>()
  if (res.success === false) throw new Error(res.message || '指定案件失败')
}

/** 重新处理（匹配失败/下载失败后重跑；已手动绑定的案件会被保留） */
export async function retryCourtSms(smsId: number): Promise<void> {
  await automationApi.post(`court-sms/${smsId}/retry`)
}

/** 删除短信记录（自测造的数据用它清理） */
export async function deleteCourtSms(smsId: number): Promise<void> {
  await automationApi.delete(`court-sms/${smsId}`)
}

/**
 * 终止并彻底删除短信处理任务：清掉 Django-Q 里的重试调度与排队任务
 * （含下载爬虫的退避重试），删除短信记录与下载任务。任务卡住/反复
 * 失败时用户主动放弃用。
 */
export async function abortCourtSmsTask(smsId: number): Promise<void> {
  const res = await automationApi
    .post(`court-sms/${smsId}/abort-and-delete`)
    .json<{ success?: boolean; message?: string }>()
  if (res.success === false) throw new Error(res.message || '停止任务失败')
}
