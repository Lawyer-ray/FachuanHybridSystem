/**
 * 出站消息组装：附件上传与引用块拼接（从 store.send 抽出，控制单文件规模）。
 *
 * 附件不进模型上下文——上传后消息里附「[已上传附件：name (attachment_id=…)]」
 * 引用块，模型用 mcp__fachuan__read_agent_attachment(id) 在服务端读正文。
 */

import * as copilotApi from './api'
import type { AgentAttachmentReceipt } from './types'

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
 * 上传待发附件并组装出站消息。
 *
 * - 无附件：直接返回原文；
 * - 有附件：逐个上传（任一失败返回 null——本轮不发、chips 保留可重试，
 *   重试时已成功的走缓存），成功后在原文后附引用块。
 *
 * 上传在途/收尾的状态落点（uploadingAttachments/pendingFiles）由调用方
 * store.send 负责；本模块只做纯出站组装。
 */
export async function uploadAttachmentsAndCompose(
  sessionId: string,
  trimmed: string,
  files: File[],
): Promise<OutgoingMessage | null> {
  if (files.length === 0) return { composed: trimmed }
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
  // 消息即将发出：回执已写进正文引用，缓存使命完成
  for (const key of uploadReceipts.keys()) {
    if (key.startsWith(`${sessionId}:`)) uploadReceipts.delete(key)
  }
  const refs = receipts.map((r) => `[已上传附件：${r.filename} (attachment_id=${r.attachment_id})]`).join('\n')
  return { composed: `${trimmed}\n\n${refs}` }
}
