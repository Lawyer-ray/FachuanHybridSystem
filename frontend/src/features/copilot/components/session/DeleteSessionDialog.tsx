/**
 * 删除会话的二次确认（共享 ConfirmDialog 的一层薄封装）。
 *
 * 从 SessionSidebar 拆出（后者超软红线）：调用方只交给它「目标会话 + 是否
 * 在途 + 确认回调」，文案与 destructive 色调固定在这里，避免删除文案散落。
 */

import { ConfirmDialog } from '@/components/shared/ConfirmDialog'

export function DeleteSessionDialog({
  target,
  pending,
  onCancel,
  onConfirm,
}: {
  /** 待删会话；null = 关闭 */
  target: { session_id: string; title: string } | null
  pending: boolean
  onCancel: () => void
  onConfirm: (sessionId: string) => void
}) {
  return (
    <ConfirmDialog
      open={target !== null}
      onOpenChange={(v) => !v && onCancel()}
      title="删除该对话？"
      description={`「${target?.title || '未命名对话'}」的消息记录将一并删除，删除后无法恢复。`}
      confirmText="删除"
      tone="destructive"
      pending={pending}
      onConfirm={() => {
        if (target) onConfirm(target.session_id)
        onCancel()
      }}
    />
  )
}
