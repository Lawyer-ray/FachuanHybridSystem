/**
 * 出站消息组装：附件上传与引用块拼接（从 store.send 抽出，控制单文件规模）。
 *
 * 附件不进模型上下文——上传后消息里附「[已上传附件：name (attachment_id=…)]」
 * 引用块，模型用 mcp__fachuan__read_agent_attachment(id) 在服务端读正文。
 *
 * **引用块只有一套格式**：三条来源（拖拽文件/目录、输入框 `@` 引用）全部走
 * `domain/mention.ts` 的 `mentionRefBlock`，与 `domain/transcript.ts` 的
 * `SENT_REF_RE` 严格互逆。绝不为 `@` 新增第二种写法——否则历史回放的 chip 与
 * 实时 chip 会两副面孔，律师刷新一次页面就认不出自己引用过什么。
 */

import * as copilotApi from './api'
import { mentionRefBlock, type MentionInsert } from './domain'
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
 *   ——模型按 contract_id + subpath 调 read_folder_file 读绑定文件夹原文件；
 * - `@` 引用（`pendingMentions`）：不落库、不复制字节，直接按归属拼「已引用
 *   文件/目录」块（整案/整份合同带 `subpath="."` = 绑定根）。
 *
 * 上传在途/收尾的状态落点（uploadingAttachments/pendingFiles）由调用方
 * store.send 负责；本模块只做纯出站组装。
 *
 * **待发 `@` 引用由调用方传进来**（`store/turn.ts` 读 `pendingMentions` 后下发）：
 * 本模块不 import store。`store/index.ts` 顶层就 import 了本模块的
 * `resetUploadReceipts`，反向引用会形成 store → outgoing → store 的模块初始化环
 * （`useCopilot` 在环里可能是未初始化绑定），惰性 import 只是把问题推到运行期。
 */
export async function uploadAttachmentsAndCompose(
  sessionId: string,
  trimmed: string,
  files: File[],
  folderRefs: FolderRefDraft[] = [],
  mentionsToSend: readonly MentionInsert[] = [],
): Promise<OutgoingMessage | null> {
  if (files.length === 0 && folderRefs.length === 0 && mentionsToSend.length === 0) return { composed: trimmed }
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
    .filter((r) => r.ref_contract_id != null && r.ref_owner_kind != null)
    .map((r) =>
      mentionRefBlock(
        {
          kind: 'document',
          label: r.filename,
          subpath: r.ref_subpath,
          owner: { kind: r.ref_owner_kind === 'case' ? 'case' : 'contract', id: r.ref_contract_id as number },
        },
        r.attachment_id,
      ),
    )
  const dirBlocks = folderRefsDir.map((d) =>
    mentionRefBlock({ kind: 'folder', label: d.name, subpath: d.subpath, owner: { kind: d.kind, id: d.ownerId } }),
  )
  // `@` 引用：重新过一遍构建器（而不是直接拿 insert.clipboardText），保证格式
  // 变更只有一处生效；没有归属的条目拼不出协议块，留痕而不是静默吞掉
  const mentionBlocks: string[] = []
  for (const mention of mentionsToSend) {
    const block = mentionRefBlock(mention)
    if (!block) {
      console.warn('[copilot] @引用缺少归属（owner/subpath），已跳过出站块', mention)
      continue
    }
    mentionBlocks.push(block)
  }
  const uploadBlocks = receipts.map((r) => `[已上传附件：${r.filename} (attachment_id=${r.attachment_id})]`)
  const blocks = [...mentionBlocks, ...refBlocks, ...dirBlocks, ...uploadBlocks].join('\n')
  return { composed: `${trimmed}\n\n${blocks}` }
}
