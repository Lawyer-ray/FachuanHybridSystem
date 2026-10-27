import { ConfirmDialog } from '@/components/shared/ConfirmDialog'

/**
 * 破坏性删除的二次确认弹窗。
 * DeskPage（删材料包）与 Reader（删页）共用，避免同一套 AlertDialog 逐字重复两份。
 *
 * 外壳已收敛到共享 ConfirmDialog：它固定「说明 + 取消在左、确认在右」，
 * 确认按钮在 pending 时会拦住 AlertDialogAction 的自动关闭（提交没回包前
 * 框不能消失）。这里只保留本 feature 的既有 props 形状（label /
 * 「删除中…」文案），调用方无需改动。
 */
export function ConfirmDeleteDialog({
  open,
  onOpenChange,
  title,
  description,
  pending,
  onConfirm,
  label = '删除',
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: React.ReactNode
  pending?: boolean
  onConfirm: () => void
  label?: string
}) {
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      // pending 时确认按钮文案由共享件给定（不再由本组件的 label 决定）
      confirmText={label}
      tone="destructive"
      pending={pending}
      onConfirm={onConfirm}
    />
  )
}
