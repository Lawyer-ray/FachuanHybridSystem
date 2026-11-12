import type { InboxMessage } from '../types'
import { DeskDialogs } from './DeskDialogs'
import { ShareLinkPanel } from './ShareLinkPanel'

/**
 * DeskPage 的浮层挂载点：把「开关状态 + 动作」这一对胶水从页面 JSX 里挪出来。
 *
 * 页面本身不需要知道「取消归案就是把 assigning 置空」这类细节——它只知道
 * `useDeskDialogs` 给出的状态和 `useDeskJudge` 给出的动作，绑定在这里完成。
 */
export function DeskDialogHost({
  assigning,
  onAssignCancel,
  onAssignConfirm,
  deleteTarget,
  onDeleteCancel,
  onDeleteConfirm,
  deleting,
  renameTarget,
  onRenameClose,
  shareLinksOpen,
  onShareLinksOpenChange,
}: {
  assigning: InboxMessage | null
  onAssignCancel: () => void
  onAssignConfirm: (pack: InboxMessage) => void
  deleteTarget: InboxMessage | null
  onDeleteCancel: () => void
  onDeleteConfirm: () => void
  deleting: boolean
  renameTarget: InboxMessage | null
  onRenameClose: () => void
  shareLinksOpen: boolean
  onShareLinksOpenChange: (open: boolean) => void
}) {
  return (
    <>
      <DeskDialogs
        assigning={assigning}
        onAssignCancel={onAssignCancel}
        onAssignConfirm={onAssignConfirm}
        deleteTarget={deleteTarget}
        onDeleteCancel={onDeleteCancel}
        onDeleteConfirm={onDeleteConfirm}
        deleting={deleting}
        renameTarget={renameTarget}
        onRenameOpenChange={onRenameClose}
      />

      <ShareLinkPanel open={shareLinksOpen} onOpenChange={onShareLinksOpenChange} />
    </>
  )
}
