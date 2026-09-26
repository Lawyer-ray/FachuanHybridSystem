import { AssignModal } from './reader/AssignModal'
import { RenamePackDialog } from './RenamePackDialog'
import { ConfirmDeleteDialog } from './ConfirmDeleteDialog'
import type { InboxMessage } from '../types'

/**
 * DeskPage 上的三个弹窗：卡片归案（AssignModal）、删除确认、重命名。
 * 各自的目标对象与回调由父组件受控传入。
 */
export function DeskDialogs({
  assigning,
  onAssignCancel,
  onAssignConfirm,
  deleteTarget,
  onDeleteCancel,
  onDeleteConfirm,
  deleting,
  renameTarget,
  onRenameOpenChange,
}: {
  assigning: InboxMessage | null
  onAssignCancel: () => void
  onAssignConfirm: (pack: InboxMessage) => void
  deleteTarget: InboxMessage | null
  onDeleteCancel: () => void
  onDeleteConfirm: () => void
  deleting: boolean
  renameTarget: InboxMessage | null
  onRenameOpenChange: (open: boolean) => void
}) {
  return (
    <>
      {/* 卡片归案：归属 modal */}
      {assigning && (
        <AssignModal
          open
          count={assigning.segs}
          infos={[]}
          onCancel={onAssignCancel}
          onConfirm={() => onAssignConfirm(assigning)}
        />
      )}

      {/* 删除材料包：破坏性操作，右键菜单点击后先二次确认 */}
      <ConfirmDeleteDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && onDeleteCancel()}
        title={`删除「${deleteTarget?.subject}」？`}
        description="将删除该材料包及其全部附件文件，不可恢复。已归案 / 归档关联不会被动，仅移除收件箱里的拆分草稿。"
        pending={deleting}
        onConfirm={onDeleteConfirm}
      />

      {/* 重命名材料包：右键菜单打开 */}
      <RenamePackDialog
        open={!!renameTarget}
        onOpenChange={(o) => !o && onRenameOpenChange(false)}
        pack={renameTarget}
      />
    </>
  )
}
