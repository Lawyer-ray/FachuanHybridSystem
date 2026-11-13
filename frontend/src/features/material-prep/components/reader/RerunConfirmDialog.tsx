import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { matLabel } from '../../draft/labels'
import type { AutoSplitConflict } from '../../draft'
import type { DraftState } from '../../types'

/**
 * 重跑自动识别前的冲突确认框。
 *
 * ## 为什么重跑必须先问
 *
 * `applyAutoSplit` 的语义是「用云端建议**整份替换**该源的段」。律师改过正文 / 段名 /
 * 类型之后，如果直接重跑就会被静默抹掉——他既没被告知，也没机会选。这类覆盖是律师
 * 最不能接受的一类错误（改了几十分钟的东西没了），所以落草稿前必须停下来问一次。
 *
 * ## 两个选项的后果必须写清楚
 *
 * - **保留我的修改**：改过的正文搬回新分段（按页重叠匹配），但 AI 这次新分出的段落里
 *   的正文**不会**进到这些段——那几页仍是你原来那段文字。
 * - **用识别结果覆盖**：以 AI 为准，这些改动**会被覆盖**、不可撤销。
 *
 * 文案只描述后果、不替律师做价值判断：哪边更好取决于他是「刚重传了清晰版想重读」
 * 还是「已经逐字核完不想再动」，这不是产品能替他决定的。
 *
 * ## 为什么不用 ConfirmDialog
 *
 * 共享壳只有「一个确认按钮」，这里需要**两个语义对称的选项**（保留 / 覆盖）加取消，
 * 且两者都不是「破坏性」单边行为——用 AlertDialog 原语直接拼，语义更准。
 */
export function RerunConfirmDialog({
  conflicts,
  draft,
  onCancel,
  onKeepEdits,
  onOverwrite,
}: {
  /** 有冲突才渲染；空数组 = 不弹 */
  conflicts: AutoSplitConflict[]
  /** 取材料显示名用（`matLabel` 认自定义名） */
  draft: DraftState
  /** 取消 = 整次重跑不执行 */
  onCancel: () => void
  /** 保留我的修改 → applyAutoSplitPreservingEdits */
  onKeepEdits: () => void
  /** 用识别结果覆盖 → applyAutoSplit */
  onOverwrite: () => void
}) {
  if (conflicts.length === 0) return null

  return (
    <AlertDialog open onOpenChange={(open) => !open && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>重跑会覆盖你的修改，怎么处理？</AlertDialogTitle>
          <AlertDialogDescription>
            下面这些材料你改过内容。重跑识别会用 AI 的新分段替换它们。
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="flex flex-col gap-1.5">
          {conflicts.map((conflict) => (
            <div key={conflict.mi} className="rounded border border-border bg-secondary/40 px-2 py-1.5">
              <div className="text-[12.5px] font-medium">{matLabel(draft.mats, conflict.mi)}</div>
              <ul className="mt-1 flex flex-col gap-0.5">
                {conflict.edited.map((item) => (
                  <li key={item.si} className="text-[11px] text-muted-foreground">
                    「{item.name}」改过 {editedText(item.what)}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* 后果说明：两组文案逐字对应两个按钮，避免律师「点了才知道」 */}
        <div className="flex flex-col gap-1 rounded border border-amber-200 bg-amber-50/60 px-2 py-1.5 text-[11px] leading-relaxed text-amber-900">
          <p>
            <span className="font-medium">保留我的修改</span>
            ：改动都留着，但 AI 这次新分出的段落里，这些段对应的正文不会进来——那几页仍是
            你原来那段文字。
          </p>
          <p>
            <span className="font-medium">用识别结果覆盖</span>
            ：以 AI 结果为准，上面这些改动会被覆盖，且不可撤销。
          </p>
        </div>

        <AlertDialogFooter>
          {/* 不加 onClick：AlertDialogCancel 会关框，onOpenChange(false) 已经是唯一的取消出口，
              再挂一次 onClick 会让 onCancel 跑两遍（重跑逻辑被执行两次）。 */}
          <AlertDialogCancel>取消</AlertDialogCancel>
          <Button variant="outline" onClick={onOverwrite}>
            用识别结果覆盖
          </Button>
          {/* 默认焦点落在「保留我的修改」：不丢人工成果是更安全的默认 */}
          <Button autoFocus onClick={onKeepEdits}>
            保留我的修改
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** 改动类型 → 中文。顺序固定（正文/名字/类型），与 `AutoSplitConflict.edited[].what` 一致 */
function editedText(what: Array<'md' | 'name' | 'type'>): string {
  const labels: Record<'md' | 'name' | 'type', string> = {
    md: '正文',
    name: '名字',
    type: '类型',
  }
  return what.map((k) => labels[k]).join(' / ')
}
