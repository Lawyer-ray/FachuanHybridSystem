/**
 * 输入框上方的待发引用/附件迷你卡（豆包式引用的第三态：整文件引用）。
 *
 * 从 Composer 拆出（后者超软红线）：本组件自取 store（pendingRefs/pendingFiles
 * 与移除动作），对外零 props——纯展示 + 删除分发，边界干净。
 */

import { useCopilot } from '../store'
import { formatFileSize } from '../domain'
import { QuoteChip } from './RefQuote'

export function PendingChips() {
  const pendingRefs = useCopilot((s) => s.pendingRefs)
  const pendingFiles = useCopilot((s) => s.pendingFiles)
  const removeFolderRef = useCopilot((s) => s.removeFolderRef)
  const removeAttachmentFile = useCopilot((s) => s.removeAttachmentFile)
  if (pendingRefs.length === 0 && pendingFiles.length === 0) return null
  return (
    <div className="mb-1.5 flex flex-wrap gap-1.5">
      {pendingRefs.map((ref, i) => (
        <QuoteChip
          key={`${ref.kind}-${ref.ownerId}-${ref.subpath}`}
          source={ref}
          onRemove={() => removeFolderRef(i)}
          removeLabel={`移除引用 ${ref.name}`}
        />
      ))}
      {pendingFiles.map((file, i) => (
        <QuoteChip
          key={`${file.name}-${i}`}
          source={{ kind: 'contract', subpath: file.name, name: file.name }}
          meta={formatFileSize(file.size)}
          icon="attachment"
          onRemove={() => removeAttachmentFile(i)}
          removeLabel={`移除附件 ${file.name}`}
        />
      ))}
    </div>
  )
}
