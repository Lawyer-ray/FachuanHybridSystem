import { FileText, X } from 'lucide-react'
import { useCallback, useId, useRef, useState } from 'react'
import { toast } from 'sonner'

import { cn } from '@/lib/utils'

import { MATERIAL_ACCEPT, formatSize, mergeFiles } from './material-files'

/**
 * 案件材料拖放区：拖入或点选多个文件，供「提交材料」按钮一次性上传。
 *
 * 与 ToolShell 的整卡拖放分开：本组件自己接管拖放热区，卡片外层不再注册
 * dropAccept，避免一次拖放触发两套 handler。
 */
export function MaterialDropZone({
  files,
  onFilesChange,
  disabled,
}: {
  files: File[]
  onFilesChange: (files: File[]) => void
  disabled?: boolean
}) {
  const [dragOver, setDragOver] = useState(false)
  // 拖放 enter/leave 会在子元素间抖动，用深度计数只在真正离开时熄灭高亮
  const depth = useRef(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const inputId = useId()

  const accept = useCallback(
    (incoming: File[]) => {
      if (incoming.length === 0) return
      const { next, rejected } = mergeFiles(files, incoming)
      if (rejected.length > 0) {
        toast.warning(`${rejected.length} 个文件已跳过：${rejected.map((r) => `${r.name}（${r.reason}）`).join('、')}`)
      }
      if (next.length !== files.length) onFilesChange(next)
    },
    [files, onFilesChange],
  )

  const removeAt = (index: number) => {
    onFilesChange(files.filter((_, i) => i !== index))
  }

  return (
    <div className="flex flex-col gap-[7px]">
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="拖入或点击选择案件材料"
        aria-disabled={disabled}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (disabled) return
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            inputRef.current?.click()
          }
        }}
        onDragEnter={(e) => {
          if (disabled) return
          e.preventDefault()
          depth.current += 1
          setDragOver(true)
        }}
        onDragOver={(e) => {
          if (disabled) return
          e.preventDefault()
        }}
        onDragLeave={() => {
          // 深度计数：拖过子元素时 enter/leave 会交替触发，计数归零才算真正离开热区。
          // 不用 relatedTarget/contains 判断，因为各浏览器（含 jsdom）在
          // dragleave 上给的 relatedTarget 并不可靠。
          depth.current = Math.max(0, depth.current - 1)
          if (depth.current === 0) setDragOver(false)
        }}
        onDrop={(e) => {
          if (disabled) return
          e.preventDefault()
          depth.current = 0
          setDragOver(false)
          accept(Array.from(e.dataTransfer?.files ?? []))
        }}
        className={cn(
          'flex cursor-pointer flex-col items-center justify-center gap-1 rounded-[8px] border border-dashed px-2 py-[14px] text-center transition-colors',
          dragOver ? 'border-status-blue bg-status-blue-bg' : 'border-input bg-secondary/30 hover:border-ring/40 hover:bg-card',
          disabled && 'pointer-events-none opacity-60',
        )}
      >
        <span className="text-[11.5px] font-medium text-secondary-foreground">
          {dragOver ? '松开即可添加' : '拖入案件材料，或点击选择'}
        </span>
        <span className="text-[10.5px] text-muted-foreground">支持 PDF / Word / 图片，可多选，单个 ≤ 50MB</span>
      </div>
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        multiple
        accept={MATERIAL_ACCEPT}
        className="hidden"
        disabled={disabled}
        onChange={(e) => {
          accept(Array.from(e.target.files ?? []))
          // 清空 value：同一文件删掉后再选，不触发 change
          e.target.value = ''
        }}
      />

      {files.length > 0 && (
        <ul className="flex max-h-[92px] flex-col gap-1 overflow-y-auto pr-0.5">
          {files.map((file, index) => (
            <li
              key={`${file.name}-${file.size}-${file.lastModified}`}
              className="flex items-center gap-1.5 rounded-[6px] bg-secondary/50 px-1.5 py-1 text-[10.5px]"
            >
              <FileText className="h-3 w-3 flex-none text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate text-secondary-foreground" title={file.name}>
                {file.name}
              </span>
              <span className="flex-none tabular-nums text-muted-foreground">{formatSize(file.size)}</span>
              <button
                type="button"
                aria-label={`移除 ${file.name}`}
                className="flex-none rounded p-0.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                onClick={() => removeAt(index)}
                disabled={disabled}
              >
                <X className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
