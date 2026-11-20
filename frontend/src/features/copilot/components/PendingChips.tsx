/**
 * 输入框上方的待发引用/附件迷你卡（豆包式引用的第三态：整文件引用）。
 *
 * 从 Composer 拆出（后者超软红线）：本组件自取 store（pendingRefs/pendingFiles/
 * pendingMentions 与移除动作），对外零 props——纯展示 + 删除分发，边界干净。
 *
 * `pendingMentions`（输入框里 `@` 选中的案件/合同/文书/目录）用同一行的紧凑 chip
 * 呈现：显示 label，× 调 removeMention。这里**只显示 label**——出站协议块
 * （`[已引用文件：… (contract_id=…)]`）是给模型读的，塞进 chip 会把一行撑成一屏。
 */

import { FileText, Folder, Scale, ScrollText, X } from 'lucide-react'

import { useCopilot } from '../store'
import { formatFileSize } from '../domain'
import type { MentionInsert } from '../domain'
import { QuoteChip } from './RefQuote'

/** 引用种类的中文前缀（chip 上只用两个字定位「这是个什么东西」） */
const KIND_LABEL: Record<string, string> = {
  case: '案件',
  contract: '合同',
  document: '文书',
  folder: '目录',
}

const KIND_ICON = { case: Scale, contract: FileText, document: ScrollText, folder: Folder }

/** `@` 引用 chip：单行、弱色，和附件/引用卡同一行的视觉重量 */
function MentionChip({ mention, onRemove }: { mention: MentionInsert; onRemove: () => void }) {
  const Icon = KIND_ICON[mention.kind as keyof typeof KIND_ICON] ?? FileText
  return (
    <span className="flex max-w-full items-center gap-1.5 rounded-[9px] border border-border bg-card py-1 pr-1 pl-2 shadow-sm">
      <span className="flex h-[18px] w-[18px] flex-none items-center justify-center rounded-[6px] bg-primary/10 text-primary">
        <Icon className="h-3 w-3" />
      </span>
      <span className="min-w-0 truncate text-[11.5px] text-foreground" title={`${KIND_LABEL[mention.kind] ?? '引用'}：${mention.label}`}>
        {mention.label}
        {mention.kind === 'folder' ? '/' : ''}
      </span>
      <span className="flex-none text-[10px] text-muted-foreground">{KIND_LABEL[mention.kind] ?? ''}</span>
      <button
        type="button"
        className="flex h-5 w-5 flex-none items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-destructive"
        aria-label={`移除引用 ${mention.label}`}
        onClick={onRemove}
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  )
}

export function PendingChips() {
  const pendingRefs = useCopilot((s) => s.pendingRefs)
  const pendingFiles = useCopilot((s) => s.pendingFiles)
  // `?? []`：切片未挂上（旧持久化状态 / 局部 mock 的 store）时不该整块崩掉
  const pendingMentions = useCopilot((s) => s.pendingMentions) ?? []
  const removeFolderRef = useCopilot((s) => s.removeFolderRef)
  const removeAttachmentFile = useCopilot((s) => s.removeAttachmentFile)
  const removeMention = useCopilot((s) => s.removeMention)
  if (pendingRefs.length === 0 && pendingFiles.length === 0 && pendingMentions.length === 0) return null
  return (
    <div className="mb-1.5 flex flex-wrap gap-1.5">
      {pendingMentions.map((mention) => (
        <MentionChip
          key={`${mention.kind}-${mention.refId ?? mention.subpath ?? ''}-${mention.label}`}
          mention={mention}
          onRemove={() => removeMention(mention.kind, mention.refId, mention.label)}
        />
      ))}
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
