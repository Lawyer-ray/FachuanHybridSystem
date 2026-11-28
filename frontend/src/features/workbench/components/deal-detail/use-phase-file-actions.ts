import { useCallback } from 'react'
import { toast } from 'sonner'

import { listFolderEntries } from '../../api'
import type { WorkbenchDeal } from '../../types'
import type { PickedFile } from './DealDocLayout'
import { addDeliverable } from './special-phase-crud'
import { flattenTree, patchPhase, type PhaseNode } from './special-phase-tree'

/**
 * 非诉专项页的「阶段树 → 文件」三个动作：阶段目录已交付文件计数、起草落点、
 * 点右栏派生目录打开第一份文件。
 *
 * 为什么抽成 hook：三件事都同时依赖**阶段树**与**预览画布**，且都带 toast 反馈；
 * 留在页面里会把「文件从哪来、落到哪」的细节与布局 JSX 混在一起。画布状态仍由
 * `useDocPreview` 持有，阶段树仍由 `useSpecialPhases` 持有——这里只做串联。
 */
export function usePhaseFileActions({
  deal,
  tree,
  saveStages,
  openPreview,
}: {
  deal: WorkbenchDeal | null
  tree: PhaseNode[]
  /** 阶段整树落库（use-special-phases 的 saveStages） */
  saveStages: (next: PhaseNode[]) => Promise<void>
  /** 打开预览（useDocPreview 的 openPreview；走未保存改动拦截） */
  openPreview: (f: PickedFile) => void
}) {
  /** 阶段目录里已有的文件数（元信息「N 个文件」）：展开行时按实际交付物计数 */
  const fileCountOf = useCallback(
    (node: PhaseNode) => flattenTree([node]).reduce((s, x) => s + x.node.deliverables.filter((d) => !d.planned).length, 0),
    [],
  )

  /**
   * 「从 0 起草」/「＋ 起草」的落点：把计划项写进目标阶段、展开它，并**直接打开
   * 编辑器**——律师此刻要的是「马上改」，不是回到列表自己去找文件。
   */
  const draftIntoPhase = useCallback(
    (phaseKey: string, name: string) => {
      const next = patchPhase(addDeliverable(tree, phaseKey, name), phaseKey, { open: true })
      void saveStages(next)
      const hit = flattenTree(next).find((x) => x.node.key === phaseKey)
      const created = hit?.node.deliverables.at(-1)
      toast.success(`已起草《${name.replace(/^《|》$/g, '')}》`, {
        description: `落到「${hit?.node.name ?? ''}」，保存后即进入编辑器`,
      })
      if (created?.subpath) openPreview({ subpath: created.subpath, name: created.name })
    },
    [tree, saveStages, openPreview],
  )

  /**
   * 点右栏派生目录 → 展开该目录里第一份可预览的文件。
   *
   * 目录是阶段派生出来的，可能还没建（律师刚设计的阶段）或只有子目录；读不到
   * 就给一句明确提示，不静默什么都不发生。
   */
  const openFolderFromTree = useCallback(
    async (folder: string) => {
      if (!deal) return
      try {
        const res = await listFolderEntries('contract', deal.id, folder)
        const file = (res.files ?? [])[0]
        if (!file) {
          toast.info(`「${folder}」目录里还没有文件`, { description: '把交付物拖进合同文件夹后即可点开' })
          return
        }
        openPreview({ subpath: file.subpath, name: file.name, size: file.size ?? undefined, modified_at: file.modified_at })
      } catch {
        toast.info(`「${folder}」目录还不存在`, { description: '保存阶段后系统会在合同文件夹里建同名目录' })
      }
    },
    [deal, openPreview],
  )

  return { fileCountOf, draftIntoPhase, openFolderFromTree }
}
