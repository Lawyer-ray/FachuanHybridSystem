import { Upload, Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

interface DropZoneProps {
  isDragging: boolean
  isUploading: boolean
  onDragEnter: (e: React.DragEvent) => void
  onDragLeave: (e: React.DragEvent) => void
  onDragOver: (e: React.DragEvent) => void
  onDrop: (e: React.DragEvent) => void
  onClick: () => void
  /** 拖拽提示文本，默认 "拖拽文件到此处上传" */
  dragText?: string
  /** 上传中提示文本，默认 "正在上传中..." */
  uploadingText?: string
  /** 支持的文件类型标签，默认 ['PDF', 'JPG', 'PNG'] */
  acceptLabels?: string[]
  /** 底部提示文本 */
  hint?: string
  /** 无障碍标签 */
  ariaLabel?: string
}

export function DropZone({
  isDragging,
  isUploading,
  onDragEnter,
  onDragLeave,
  onDragOver,
  onDrop,
  onClick,
  dragText = '拖拽文件到此处上传',
  uploadingText = '正在上传中...',
  acceptLabels = ['PDF', 'JPG', 'PNG'],
  hint,
  ariaLabel = '上传文件',
}: DropZoneProps) {
  return (
    <div
      className={`
        relative flex min-h-[200px] cursor-pointer flex-col items-center justify-center
        rounded-lg border-2 border-dashed p-6 transition-all duration-200
        ${
          isDragging
            ? 'border-primary bg-primary/5 scale-[1.02]'
            : 'border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50'
        }
        ${isUploading ? 'pointer-events-none opacity-60' : ''}
      `}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      }}
      aria-label={ariaLabel}
    >
      {isUploading ? (
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="text-primary size-12 animate-spin" />
          <p className="text-muted-foreground text-sm">{uploadingText}</p>
        </div>
      ) : (
        <>
          <div
            className={`
              mb-4 rounded-full p-4 transition-colors
              ${isDragging ? 'bg-primary/10' : 'bg-muted'}
            `}
          >
            <Upload
              className={`size-8 ${isDragging ? 'text-primary' : 'text-muted-foreground'}`}
            />
          </div>
          <p className="text-foreground mb-1 text-center font-medium">
            {isDragging ? '松开鼠标上传文件' : dragText}
          </p>
          <p className="text-muted-foreground mb-3 text-center text-sm">
            或点击选择文件
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            {acceptLabels.map((label) => (
              <Badge key={label} variant="secondary" className="text-xs">
                {label}
              </Badge>
            ))}
          </div>
          {hint && (
            <p className="text-muted-foreground mt-2 text-xs">{hint}</p>
          )}
        </>
      )}
    </div>
  )
}
