import { useCallback, useState } from 'react'
import type { InboxMessage } from '../types'

/**
 * DeskPage 上的弹窗开关状态簇：归案（AssignModal）、删除确认、重命名、
 * 客户上传链接面板。
 *
 * 为什么成簇住在这里：四个状态同属一件事——「此刻哪一个浮层开着、开给哪个包」。
 * 它们此前与页签过滤、上传、离场动画的 state 混在页面组件里，看不出是一组；
 * 这组状态只被 DeskDialogs / ShareLinkPanel 消费，页面本身不需要认识它们。
 *
 * 语义保持原样：三个包级浮层的目标对象各自独立（`null` 即关闭），
 * 打开一个不会顺手关掉另一个。
 */
export function useDeskDialogs() {
  const [assigning, setAssigning] = useState<InboxMessage | null>(null)
  // 待确认删除的材料包（破坏性操作，右键后先经 AlertDialog 确认）
  const [deleteTarget, setDeleteTarget] = useState<InboxMessage | null>(null)
  // 待重命名的材料包（右键菜单打开），null 时关闭
  const [renameTarget, setRenameTarget] = useState<InboxMessage | null>(null)
  // 客户上传链接管理面板
  const [shareLinksOpen, setShareLinksOpen] = useState(false)

  const closeAssign = useCallback(() => setAssigning(null), [])
  const closeDelete = useCallback(() => setDeleteTarget(null), [])
  const closeRename = useCallback(() => setRenameTarget(null), [])

  return {
    assigning,
    setAssigning,
    closeAssign,
    deleteTarget,
    setDeleteTarget,
    closeDelete,
    renameTarget,
    setRenameTarget,
    closeRename,
    shareLinksOpen,
    setShareLinksOpen,
  }
}
