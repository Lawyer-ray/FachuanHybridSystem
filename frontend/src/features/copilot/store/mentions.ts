/**
 * store slice：待发送的 `@` 引用（案件 / 合同 / 文书 / 文件夹）。
 *
 * 只做三件事：去重加、移除、清空。**不做取数**——候选从哪来是 `api.ts` 与
 * 各数据源的事，store 不该知道「案件要调哪个端点」。
 *
 * 去重键用 `(kind, refId, label)` 三元组而不是 `refId` 单值：文件夹没有业务 id
 * （靠 ownerId + subpath 定位），而同一 id 的文书可能在不同案件下同号。
 */

import type { MentionInsert } from '../domain'
import type { CopilotState } from '../types'
import type { Slice } from './slice'

export type MentionSlice = Pick<
  CopilotState,
  'pendingMentions' | 'addMention' | 'removeMention' | 'clearMentions'
>

/** 两条引用是否指向同一个对象（去重与移除共用，避免两处判据漂移） */
export function sameMention(a: MentionInsert, b: MentionInsert): boolean {
  return a.kind === b.kind && a.refId === b.refId && a.label === b.label
}

export const createMentionSlice: Slice<MentionSlice> = (set) => ({
  pendingMentions: [],

  addMention: (insert) =>
    set((s) => {
      if (s.pendingMentions.some((existing) => sameMention(existing, insert))) return s
      return { pendingMentions: [...s.pendingMentions, insert] }
    }),

  removeMention: (kind, refId, label) =>
    set((s) => {
      const next = s.pendingMentions.filter(
        (existing) => !sameMention(existing, { kind, refId, label, clipboardText: '' }),
      )
      if (next.length === s.pendingMentions.length) return s
      return { pendingMentions: next }
    }),

  clearMentions: () => set((s) => (s.pendingMentions.length === 0 ? s : { pendingMentions: [] })),
})
