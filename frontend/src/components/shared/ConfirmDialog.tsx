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
 * 标准二次确认弹窗外壳（AlertDialog 的正确用法封装）。
 *
 * 直接铺 @/components/ui/alert-dialog 的 6 个部件太啰嗦，各处手拼时容易漏
 * AlertDialogDescription（Radix 会打 a11y 警告）或把取消/确认顺序写反——
 * 这里固定「说明 + 取消在左、确认在右」的结构，调用方只给文案和回调。
 *
 * 不用 Dialog 而是 AlertDialog：模态语义上不允许点遮罩/Esc 误关，
 * 且焦点默认落在取消上，防止回车误触发破坏性操作。
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmText = '确定',
  cancelText = '取消',
  tone = 'default',
  pending = false,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: React.ReactNode
  /** 副说明。没有副文案也要传一个（Radix 缺 Description 会告警），一般给后果说明 */
  description?: React.ReactNode
  confirmText?: string
  cancelText?: string
  /** destructive = 删除/覆盖等不可逆操作（红底确认按钮） */
  tone?: 'default' | 'destructive'
  /** 提交中：按钮文案换成「处理中…」并禁止重复点击 */
  pending?: boolean
  onConfirm: () => void
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>{cancelText}</AlertDialogCancel>
          <AlertDialogAction
            // 变体走 Button 的 variant，别手拼 bg-destructive：暗色下 variant 自带 60% 底色
            variant={tone === 'destructive' ? 'destructive' : 'default'}
            // AlertDialogAction 默认会立刻关闭弹窗；pending 中必须留住，否则
            // 提交还没回包框就没了，用户看不到「处理中」也看不到失败原因
            onClick={(e) => {
              if (pending) {
                e.preventDefault()
                return
              }
              onConfirm()
            }}
          >
            {pending ? '处理中…' : confirmText}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
