import { OcrPanel } from './OcrPanel'
import { AssignModal } from './AssignModal'
import { RenamePackDialog } from '../RenamePackDialog'
import { ConfirmDeleteDialog } from '../ConfirmDeleteDialog'
import type { AssignInfo, DraftState, InboxMessageDetail, OcrPending, PageKey } from '../../types'

/**
 * Reader 上的弹窗组合：OCR 取字确认面板、归案归属、删除所选页确认、重命名材料包。
 * 各自的开关与回调由父组件受控传入，本组件只负责接线与转发。
 */
export function ReaderDialogs({
  draft,
  detail,
  ocrPending,
  ocrFrom,
  ocrTo,
  onOcrText,
  onOcrRedo,
  onOcrCancel,
  onOcrOk,
  showAssign,
  onAssignCancel,
  onAssignConfirm,
  deleteTarget,
  onDeleteCancel,
  onDeleteConfirm,
  renaming,
  onRenamingChange,
}: {
  draft: DraftState
  detail: InboxMessageDetail
  ocrPending: OcrPending | null
  ocrFrom: string
  ocrTo: string
  onOcrText: (v: string) => void
  onOcrRedo: () => void
  onOcrCancel: () => void
  onOcrOk: () => void
  showAssign: boolean
  onAssignCancel: () => void
  onAssignConfirm: (assign: AssignInfo) => void
  deleteTarget: PageKey[] | null
  onDeleteCancel: () => void
  onDeleteConfirm: () => void
  renaming: boolean
  onRenamingChange: (open: boolean) => void
}) {
  return (
    <>
      {/* OCR 确认面板 */}
      {ocrPending && (
        <OcrPanel
          pending={ocrPending}
          fromLabel={ocrFrom}
          toLabel={ocrTo}
          onText={onOcrText}
          onRedo={onOcrRedo}
          onCancel={onOcrCancel}
          onOk={onOcrOk}
        />
      )}

      {/* 归案归属 */}
      {showAssign && (
        <AssignModal
          open
          count={draft.segs.length}
          infos={draft.infos}
          onCancel={onAssignCancel}
          onConfirm={onAssignConfirm}
        />
      )}

      {/* 删除所选页：破坏性操作，二次确认（与删材料包共用 ConfirmDeleteDialog） */}
      <ConfirmDeleteDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && onDeleteCancel()}
        title={`确认删除所选 ${deleteTarget?.length ?? 0} 页？`}
        description="将从材料拆分中移除这些页并清空空段，仅影响拆分草稿，不影响原始文件。"
        onConfirm={onDeleteConfirm}
      />

      {/* 重命名材料包标题：标题栏铅笔按钮打开 */}
      <RenamePackDialog
        open={renaming}
        onOpenChange={onRenamingChange}
        pack={detail}
      />
    </>
  )
}
