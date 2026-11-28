import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

/**
 * 「文档里有未保存的修改」拦一下。
 *
 * **为什么由页面出这个弹窗**：能弄丢画布内容的入口不止卡上的 X——点文件夹树里的
 * 另一份文件、从案件卡打开别的文书，都会让画布换人。确认因此挂在整个页面这一层，
 * 而不是长在卡片内部（卡片只知道「我要关了」，不知道是谁要关）。
 *
 * 只有两个选择：继续编辑（什么都不做）或放弃修改。**不做「保存并离开」**：
 * 保存是 DS 的 forcesave，落盘发生在回调里（1–3 秒），离开时没法等它——给一个
 * 「看着保存了、其实还没写完就被销毁」的按钮，比不给更危险。
 */
export function UnsavedChangesDialog({
  open,
  onStay,
  onLeave,
  title = '文档里还有未保存的修改',
  description = '现在离开会丢掉这些修改。要保留的话，先点「继续编辑」，在文档里按 ⌘S（或点右上角「保存」）写回原文件后再关。',
  stayLabel = '继续编辑',
  leaveLabel = '放弃修改',
}: {
  open: boolean
  /** 继续编辑（什么都不做，留在文档里） */
  onStay: () => void
  /** 放弃这次未保存的修改，继续原本的动作（关文档 / 换文件） */
  onLeave: () => void
  /** 文案可换：项目编辑页复用它，说的是「表单」而不是「画布」 */
  title?: string
  description?: string
  stayLabel?: string
  leaveLabel?: string
}) {
  return (
    <AlertDialog
      open={open}
      onOpenChange={(v) => {
        if (!v) onStay()
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onStay}>{stayLabel}</AlertDialogCancel>
          <AlertDialogAction onClick={onLeave}>{leaveLabel}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
