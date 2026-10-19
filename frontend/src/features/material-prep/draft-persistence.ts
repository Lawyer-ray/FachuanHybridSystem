/**
 * 阅读器草稿的防抖落盘（store.ts 下沉出来的持久化关注点）。
 *
 * 模块级「最新待存草稿」+ 单一计时器：连续 update 只排队最后一次，
 * 到点落一次盘；immediate（关阅读器 / 打标状态等场景）则取消防抖马上写。
 * 保存失败 toast + reject 由调用方决定是否吞掉。
 */

import { toast } from 'sonner'

import { saveDraft } from './api'
import type { DraftState } from './types'

let saveTimer: ReturnType<typeof setTimeout> | null = null
let latestDraft: DraftState | null = null
let latestId = 0

/** 防抖保存草稿（默认 450ms）；已有排队时并入现有批次（返回 null 表示本次只更新待存值） */
export function scheduleSave(draft: DraftState, id: number, immediate = false): Promise<void> | null {
  latestDraft = draft
  latestId = id
  // 立即保存：取消待执行的防抖，马上落一次盘
  if (immediate && saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  if (saveTimer) return null
  return new Promise((resolve, reject) => {
    saveTimer = setTimeout(() => {
      saveTimer = null
      const d = latestDraft
      const mid = latestId
      if (!d) return resolve()
      saveDraft(mid, d)
        .then(() => resolve())
        .catch((e: unknown) => {
          toast.error('拆分草稿保存失败，请检查后端连接')
          reject(e instanceof Error ? e : new Error(String(e)))
        })
    }, immediate ? 0 : 450)
  })
}

/** 丢弃未落盘的防抖保存（登出重置用）：取消计时器并忘掉待存草稿。
 *  登出后 token 已清，保存只会报错；草稿按丢弃处理。 */
export function discardPendingSave(): void {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  latestDraft = null
}
