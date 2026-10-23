/**
 * 出站消息组装：附件上传与引用块拼接（从 store.send 抽出，控制单文件规模）。
 *
 * 附件不进模型上下文——上传后消息里附「[已上传附件：name (attachment_id=…)]」
 * 引用块，模型用 mcp__fachuan__read_agent_attachment(id) 在服务端读正文。
 */

import * as copilotApi from './api'

export interface OutgoingMessage {
  /** 实际发出的消息（原文本 + 附件引用块） */
  composed: string
}

/**
 * 上传待发附件并组装出站消息。
 *
 * - 无附件：直接返回原文；
 * - 有附件：逐个上传（任一失败返回 null——本轮不发、chips 保留可重试），
 *   成功后清空 chips 并在原文后附引用块。
 */
export async function uploadAttachmentsAndCompose(
  sessionId: string,
  trimmed: string,
  files: File[],
  onStart: () => void,
  onFinish: (patch: { uploadingAttachments: boolean; pendingFiles?: File[] }) => void,
): Promise<OutgoingMessage | null> {
  if (files.length === 0) return { composed: trimmed }
  onStart()
  const receipts: { attachment_id: string; filename: string }[] = []
  try {
    for (const file of files) {
      receipts.push(await copilotApi.uploadAttachment(sessionId, file))
    }
  } catch {
    onFinish({ uploadingAttachments: false })
    return null
  }
  onFinish({ uploadingAttachments: false, pendingFiles: [] })
  const refs = receipts.map((r) => `[已上传附件：${r.filename} (attachment_id=${r.attachment_id})]`).join('\n')
  return { composed: `${trimmed}\n\n${refs}` }
}
