import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { DOC_SIDE_BY_SIDE_MIN, type PickedFile } from './DealDocLayout'
import type { FolderEntryMutation } from './folder-tree-types'
import { useDocDirtyGuard } from './use-doc-dirty-guard'
import { useNetWidth } from './use-net-width'

/**
 * 详情页「右栏就地预览」的整台机器（诉讼页 `DealDetailPage` 与非诉页 `NonLitDetailPage` 共用）。
 *
 * 为什么抽出来：两页里这一整块是**逐字重复**的 —— `picked` / `immersive` 两个状态、
 * `pickedRef` 实时快照、`closePreview` 的脏标记拦截、`onFolderMutated` 的命中判定、
 * 以及由 `netWidth` 决定的「并排 / 通栏」。重复的代价不是行数，而是**规则**：
 * 「树里改名/删除后要不要把预览关掉」改一次得改两处，漏一处就是律师看到标题还是旧名、
 * 高亮消失、⌘S 打到一个不存在的文件上，而界面说「保存成功」。
 *
 * 两页唯一的真实差异是**归属判定**：非诉页只有合同文件（认 `ev.kind === 'contract'`
 * 且 `ev.ownerId === deal.id`），诉讼页按当前选中文件的 `kind`/`ownerId` 比。所以判定
 * 由调用方注入 `isStale`，其余全部收在这里。
 *
 * `isStale` **必须是稳定引用**（调用方用 `useCallback` 包），否则 `onFolderMutated`
 * 每次渲染都换新函数，挂在 `FolderTree` 上的 memo 会失效。
 */
export interface UseDocPreviewOptions<T extends PickedFile> {
  /** 「树里被改名/删除的这一条，是否就是正在预览的那份」——两页口径不同，由页面注入 */
  isStale: (ev: FolderEntryMutation, picked: T) => boolean
}

export function useDocPreview<T extends PickedFile>({ isStale }: UseDocPreviewOptions<T>) {
  /** 正在预览的文件（null = 未选中） */
  const [picked, setPicked] = useState<T | null>(null)
  /** 沉浸态（`DealDocLayout` 的 ④）：关掉文档时要一起复位，否则下一份打开就是全屏 */
  const [immersive, setImmersive] = useState(false)

  /**
   * 画布里有未保存的改动时，关文档 / 换文件先拦一下。
   *
   * 三个入口都能弄丢编辑：卡片右上角的 X、点文件夹树里的另一份、从案件卡打开别的文书。
   * 确认因此挂在页面这一层（见 `useDocDirtyGuard` 的注释）。
   */
  const doc = useDocDirtyGuard()
  const guardDirty = doc.guard
  const markDirty = doc.markDirty

  /**
   * 当前预览路径的**实时快照**。
   *
   * 文件夹树里改名/删除成功后要立刻判断「被弄掉的是不是正在看的那份」，而回调是
   * 事件式的、读 state 会读到上一轮渲染的值。
   */
  const pickedRef = useRef<T | null>(null)
  useEffect(() => {
    pickedRef.current = picked
  }, [picked])

  /** 打开一份文件（走脏标记拦截：有未保存改动先问） */
  const openPreview = useCallback((f: T) => guardDirty(() => setPicked(f)), [guardDirty])

  /** 关预览：沉浸态必须一起复位 */
  const closePreview = useCallback(() => {
    guardDirty(() => {
      setImmersive(false)
      setPicked(null)
    })
  }, [guardDirty])

  /**
   * 树里改名 / 删除后，把还在指着旧路径的画布关掉。
   *
   * 不处理的话：标题还是旧名字、高亮消失、画布仍可编辑，⌘S 打到一个不存在的文件上。
   */
  const onFolderMutated = useCallback(
    (ev: FolderEntryMutation) => {
      const cur = pickedRef.current
      if (!cur || !isStale(ev, cur)) return
      setImmersive(false)
      setPicked(null)
      markDirty(false)
      toast.info(ev.type === 'delete' ? '正在预览的文件已被删除，预览已关闭' : '文件已改名，预览已关闭')
    },
    [isStale, markDirty],
  )

  /**
   * 文档栏形态（见 `DealDocLayout` 的四态表）：净宽够 → 文档在右（可拖宽）；
   * 净宽不够的宽屏 → 文档通栏置顶。判定用**净宽**而不是视口：并排 AI 助手会吃掉
   * 数百像素，问视口等于没问。
   */
  const netWidth = useNetWidth()
  const docSideBySide = Boolean(picked) && netWidth >= DOC_SIDE_BY_SIDE_MIN

  return {
    picked,
    setPicked,
    immersive,
    setImmersive,
    openPreview,
    closePreview,
    onFolderMutated,
    netWidth,
    docSideBySide,
    /** `pending` / `stay` / `leave` 给页面的 `<UnsavedChangesDialog>` 用 */
    doc,
  }
}
