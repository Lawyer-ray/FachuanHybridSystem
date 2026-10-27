/**
 * store slice：待发草稿（附件 chips / 文件夹引用 chips / 框选引用）。
 *
 * 纯 chips 管理，**不碰网络**：真正的上传发生在 send（outgoing.ts 复用回执，
 * 部分失败重试不重复上传）。同 contractId+subpath 的文件夹引用去重。
 */

import { splitAttachmentFiles } from '../domain'
import type { CopilotState } from '../types'
import type { Slice } from './slice'

export type AttachmentSlice = Pick<
  CopilotState,
  'addAttachmentFiles' | 'removeAttachmentFile' | 'addFolderRef' | 'removeFolderRef' | 'setPendingQuote'
>

export const createAttachmentSlice: Slice<AttachmentSlice> = (set) => ({
  addAttachmentFiles: (files) => {
    const { accepted, rejected } = splitAttachmentFiles(Array.from(files))
    if (accepted.length === 0 && rejected.length === 0) return
    set((s) => ({
      pendingFiles: [...s.pendingFiles, ...accepted],
      draggingFiles: false,
      lastError: rejected.length > 0 ? `部分文件未添加：${rejected.join('；')}` : s.lastError,
    }))
  },

  removeAttachmentFile: (index) => {
    set((s) => ({ pendingFiles: s.pendingFiles.filter((_, i) => i !== index) }))
  },

  addFolderRef: (draft) => {
    set((s) => {
      if (s.pendingRefs.some((r) => r.kind === draft.kind && r.ownerId === draft.ownerId && r.subpath === draft.subpath)) return s
      return { pendingRefs: [...s.pendingRefs, draft] }
    })
  },

  removeFolderRef: (index) => {
    set((s) => ({ pendingRefs: s.pendingRefs.filter((_, i) => i !== index) }))
  },

  /** 框选引用（豆包式）：新选区直接覆盖旧的——律师的意图就是「换成这段」 */
  setPendingQuote: (quote) => {
    set({ pendingQuote: quote })
  },
})
