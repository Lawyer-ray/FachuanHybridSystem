/**
 * 出站消息组装：附件上传与引用块拼接（从 store.send 抽出，控制单文件规模）。
 *
 * 附件不进模型上下文——上传后消息里附「[已上传附件：name (attachment_id=…)]」
 * 引用块，模型用 mcp__fachuan__read_agent_attachment(id) 在服务端读正文。
 */

import * as copilotApi from './api'
import type { AgentAttachmentReceipt, FolderRefDraft } from './types'

export interface OutgoingMessage {
  /** 实际发出的消息（原文本 + 附件引用块） */
  composed: string
}

/**
 * 上传成功的回执缓存（会话 id + 文件指纹 → 回执）。
 *
 * 部分失败重试时，已成功的附件直接复用回执、不再重复上传（否则服务端会
 * 多存一份孤儿存档）；消息真正发出后按会话清掉，避免缓存无限增长。
 */
const uploadReceipts = new Map<string, AgentAttachmentReceipt>()

const receiptKey = (sessionId: string, file: File) => `${sessionId}:${file.name}:${file.size}:${file.lastModified}`

/** 清空回执缓存（登出/测试用） */
export function resetUploadReceipts(): void {
  uploadReceipts.clear()
}

/**
 * 上传待发附件、落库文件夹引用并组装出站消息。
 *
 * - 两者皆无：直接返回原文；
 * - 附件：逐个上传（任一失败返回 null——本轮不发、chips 保留可重试，
 *   重试时已成功的走缓存），成功后在原文后附引用块；
 * - 文件夹引用：逐个落库（POST folder-refs 拿回执），附「已引用文件」块
 *   ——模型按 contract_id + subpath 调 read_folder_file 读绑定文件夹原文件。
 *
 * 上传在途/收尾的状态落点（uploadingAttachments/pendingFiles）由调用方
 * store.send 负责；本模块只做纯出站组装。
 */
export async function uploadAttachmentsAndCompose(
  sessionId: string,
  trimmed: string,
  files: File[],
  folderRefs: FolderRefDraft[] = [],
): Promise<OutgoingMessage | null> {
  if (files.length === 0 && folderRefs.length === 0) return { composed: trimmed }
  const receipts: AgentAttachmentReceipt[] = []
  try {
    for (const file of files) {
      const key = receiptKey(sessionId, file)
      const cached = uploadReceipts.get(key)
      if (cached) {
        receipts.push(cached)
        continue
      }
      const receipt = await copilotApi.uploadAttachment(sessionId, file)
      uploadReceipts.set(key, receipt)
      receipts.push(receipt)
    }
  } catch {
    return null
  }
  // 文件引用落附件（按 kind 走合同/案件绑定）；目录引用不落附件——
  // 提示块让模型用 list_folder_files 自行浏览目录再按需读文件
  let refReceipts: AgentAttachmentReceipt[] = []
  const fileRefs = folderRefs.filter((d) => !d.isFolder)
  const folderRefsDir = folderRefs.filter((d) => d.isFolder)
  if (fileRefs.length > 0) {
    try {
      refReceipts = await Promise.all(
        fileRefs.map((d) => copilotApi.createFolderRef(sessionId, d.kind, d.ownerId, d.subpath)),
      )
    } catch {
      return null
    }
  }
  // 消息即将发出：回执已写进正文引用，缓存使命完成
  for (const key of uploadReceipts.keys()) {
    if (key.startsWith(`${sessionId}:`)) uploadReceipts.delete(key)
  }
  const refBlocks = refReceipts
    .filter((r) => r.ref_contract_id != null)
    .map((r) => {
      const idKey = r.ref_owner_kind === 'case' ? 'case_id' : 'contract_id'
      return `[已引用文件：${r.filename} (attachment_id=${r.attachment_id}, ${idKey}=${r.ref_contract_id}, subpath="${r.ref_subpath}")]`
    })
  const dirBlocks = folderRefsDir.map(
    (d) =>
      `[已引用目录：${d.name} (${d.kind === 'case' ? 'case_id' : 'contract_id'}=${d.ownerId}, subpath="${d.subpath}")]`,
  )
  const uploadBlocks = receipts.map((r) => `[已上传附件：${r.filename} (attachment_id=${r.attachment_id})]`)
  const blocks = [...refBlocks, ...dirBlocks, ...uploadBlocks].join('\n')
  return { composed: `${trimmed}\n\n${blocks}` }
}
