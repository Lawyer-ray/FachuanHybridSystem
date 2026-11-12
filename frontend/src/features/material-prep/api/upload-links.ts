import type { components } from '@/types/api-schema'
import { inboxApi } from './inbox-packs'

/* ============ 客户上传链接（/api/v1/inbox/upload-links） ============ */

/** 链接列表行（生成物 UploadLinkOut；token 明文绝不在列表出现） */
export type UploadLinkRow = components['schemas']['UploadLinkOut']

/** 创建/轮换响应（生成物 UploadLinkCreatedOut；token 明文仅此一次） */
export type UploadLinkCreated = components['schemas']['UploadLinkCreatedOut']

export async function createUploadLink(payload: {
  title: string
  note?: string
  client_name?: string
  contract_id?: number | null
  expires_days?: number
}): Promise<UploadLinkCreated> {
  return inboxApi.post('upload-links', { json: payload }).json<UploadLinkCreated>()
}

export async function listUploadLinks(): Promise<UploadLinkRow[]> {
  return inboxApi.get('upload-links').json<UploadLinkRow[]>()
}

export async function revokeUploadLink(id: number): Promise<UploadLinkRow> {
  return inboxApi.post(`upload-links/${id}/revoke`).json<UploadLinkRow>()
}

/**
 * 彻底删除链接（从列表消失）。与作废的区别：作废只改状态、记录留着可审计；
 * 删除是真的不显示了，用于清理已作废的历史。
 *
 * 后端限**创建人本人或管理员**（其余返回 404），已收材料包不受影响
 * （`InboxMessage.upload_link` 是 SET_NULL，只置空来源指针）。
 */
export async function deleteUploadLink(id: number): Promise<void> {
  await inboxApi.delete(`upload-links/${id}`)
}

export async function rotateUploadLink(id: number): Promise<UploadLinkCreated> {
  return inboxApi.post(`upload-links/${id}/rotate`).json<UploadLinkCreated>()
}

/** 组装客户分享 URL：公开页路由 /u/:token，用当前站点 origin（公网/内网各自成立） */
export function buildShareUrl(token: string): string {
  return `${window.location.origin}/u/${token}`
}
