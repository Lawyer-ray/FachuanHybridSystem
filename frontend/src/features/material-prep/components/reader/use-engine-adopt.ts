import { useCallback, useRef, useState } from 'react'

import { blockKeyOf } from '../../draft/block-keys'
import type { DraftState } from '../../types'

/**
 * 「采用某侧引擎文本 → 进编辑态 → 保存后自动勾选已核对」这套编排。
 *
 * ## 为什么「采用」不是直接写入
 *
 * 两侧都可能错。实测同一处姓名被两个引擎读成三个不同结果（原件那个字本身
 * 模糊/异体），此时点任何一边的「采用」都是把错的写进诉状引用。
 *
 * 所以采用 = **拿该侧全文当起点进编辑态**：
 * - 两侧都对 → 直接回车确认（多按一次，换掉「不可逆误写」的风险）
 * - 两侧都错 → 在预填基础上改那几个字，不用对着 60+ 字从零手打
 *
 * ## 为什么保存后自动勾「已核对」
 *
 * 「看了两侧文本 → 确认/修正 → 落库」本身就是一次完整核对。让他再回清单
 * 手动勾一次是重复劳动。手工改正文（非分歧发起）不勾——那不是核对过分歧。
 */
export function useEngineAdopt(params: {
  draft: DraftState
  focusedSeg: number
  onToggleChecked: (key: string, checked: boolean) => void
  onGotoPage: (si: number, pageNo: number) => void
  onOpenMd: () => void
}) {
  const { draft, focusedSeg, onToggleChecked, onGotoPage, onOpenMd } = params

  const [editRequest, setEditRequest] = useState<{
    key: string
    seed?: string | null
  } | null>(null)

  /** 这次编辑由哪条分歧发起；保存后据此自动勾选 */
  const pendingCheckedKey = useRef<string | null>(null)

  const adopt = useCallback(
    (pageNo: number, text: string, _engine: string, disagreeKey?: string) => {
      const seg = draft.segs[focusedSeg]
      if (!seg?.blocks?.length) return
      const needle = text.trim()
      if (!needle) return
      // 定位口径与「采用」一致：同页 + 块文本包含该引擎文本。
      // 找不到就不动——宁可不改，也不要把文字写到错误的块上。
      const idx = seg.blocks.findIndex((b) => b.page === pageNo && (b.text ?? '').includes(needle))
      if (idx < 0) return
      const key = blockKeyOf(seg, seg.blocks[idx]!, idx)
      pendingCheckedKey.current = disagreeKey ?? null
      setEditRequest({ key, seed: needle })
      onOpenMd()
      onGotoPage(focusedSeg, pageNo)
    },
    [draft.segs, focusedSeg, onGotoPage, onOpenMd],
  )

  /** 正文某行保存后调用：若这次编辑是分歧发起的，自动标为已核对 */
  const commit = useCallback(() => {
    const dk = pendingCheckedKey.current
    if (!dk) return
    pendingCheckedKey.current = null
    onToggleChecked(dk, true)
  }, [onToggleChecked])

  /** 请求被消费后清空（供 SegmentMarkdown 的 onEditRequestHandled） */
  const clearRequest = useCallback(() => setEditRequest(null), [])

  /**
   * 直接请求编辑某一块（不带种子）——页面框双击进来的那条路。
   * 与 `adopt` 的区别：它不预填、也不记「待勾选的分歧」。
   */
  const requestEdit = useCallback((req: { key: string; seed?: string | null }) => {
    pendingCheckedKey.current = null
    setEditRequest(req)
  }, [])

  return { editRequest, adopt, commit, clearRequest, requestEdit }
}
