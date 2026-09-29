import { useRef, useState, type DragEvent, type ReactNode } from 'react'
import { toast } from 'sonner'

import { cn } from '@/lib/utils'

/** 共用的转圈图标（四张卡 busy 态都用它） */
export function Spinner() {
  return (
    <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity=".25" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

/** 从 accept 串（".doc,.docx" 等）提取扩展名列表，供拖放过滤 */
function acceptExts(accept?: string): string[] {
  return (accept ?? '')
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter((s) => s.startsWith('.'))
}

/** 整卡拖放处理：按 accept 过滤拖入文件，全部不匹配时提示 */
function useCardDrop(accept: string | undefined, onDropFiles: ((files: File[]) => void) | undefined) {
  const [dragOver, setDragOver] = useState(false)
  const depth = useRef(0)

  const handlers = onDropFiles
    ? {
        onDragEnter: (e: DragEvent) => {
          e.preventDefault()
          depth.current += 1
          setDragOver(true)
        },
        onDragOver: (e: DragEvent) => {
          e.preventDefault()
        },
        onDragLeave: (e: DragEvent) => {
          // 只在真正离开卡片（relatedTarget 不在卡片内）时熄灭高亮
          if (e.currentTarget.contains(e.relatedTarget as Node | null)) return
          depth.current = 0
          setDragOver(false)
        },
        onDrop: (e: DragEvent) => {
          e.preventDefault()
          depth.current = 0
          setDragOver(false)
          const files = Array.from(e.dataTransfer?.files ?? [])
          if (files.length === 0) return
          const exts = acceptExts(accept)
          const matched = exts.length === 0 ? files : files.filter((f) => exts.some((ext) => f.name.toLowerCase().endsWith(ext)))
          if (matched.length === 0) {
            toast.warning(`请拖入 ${exts.join(' / ')} 文件`)
            return
          }
          onDropFiles(matched)
        },
      }
    : {}

  return { dragOver, cardDragProps: handlers }
}

/** 工具卡外壳：图标 + 标题 + 后端端点注释 + 内容区。
 *  headerExtra 放头部右侧小入口；给 dropAccept + onDropFiles 即成为拖放目标，
 *  拖文件悬停时整卡高亮（浏览器默认「丢上来就打开文件」由 ToolDock 全局拦截）。 */
export function ToolShell({
  icon,
  title,
  endpoint,
  headerExtra,
  dropAccept,
  onDropFiles,
  children,
}: {
  icon: ReactNode
  title: string
  endpoint: string
  headerExtra?: ReactNode
  dropAccept?: string
  onDropFiles?: (files: File[]) => void
  children: ReactNode
}) {
  const { dragOver, cardDragProps } = useCardDrop(dropAccept, onDropFiles)
  return (
    <div
      {...cardDragProps}
      className={cn(
        'relative flex flex-col rounded-[12px] border bg-secondary/30 p-[13px] transition-colors',
        dragOver ? 'border-status-blue bg-status-blue-bg' : 'border-border',
      )}
    >
      {dragOver && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-[12px] bg-background/70">
          <span className="rounded-[8px] border border-status-blue/40 bg-status-blue-bg px-3 py-1.5 text-[12.5px] font-semibold text-status-blue">
            松开以选择文件
          </span>
        </div>
      )}
      <div className="mb-[11px] flex items-center gap-2.5">
        <div className="flex h-7 w-7 flex-none items-center justify-center rounded-[8px] border border-border bg-card text-secondary-foreground">
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[12.5px] leading-[1.2] font-semibold">{title}</div>
          <div className="mt-[2px] truncate font-mono text-[9px] text-muted-foreground" title={endpoint}>
            {endpoint}
          </div>
        </div>
        {headerExtra}
      </div>
      {children}
    </div>
  )
}

/** 虚线文件选择框（要素式转换 / DOC 转 DOCX 共用） */
export function FilePicker({
  label,
  hint,
  accept,
  multiple,
  disabled,
  onPick,
}: {
  label: string
  hint: string
  accept: string
  multiple?: boolean
  disabled?: boolean
  onPick: (files: File[]) => void
}) {
  return (
    <label
      className={cn(
        'flex cursor-pointer items-center gap-2 rounded-[8px] border border-dashed border-input bg-secondary/30 px-[9px] py-[6px] transition-colors hover:border-ring/40 hover:bg-card',
        disabled && 'pointer-events-none opacity-60',
      )}
    >
      <input
        type="file"
        accept={accept}
        multiple={multiple}
        className="hidden"
        disabled={disabled}
        onChange={(e) => onPick(Array.from(e.target.files ?? []))}
      />
      <span className="text-[11px] font-medium whitespace-nowrap text-secondary-foreground">{label}</span>
      <span className="truncate text-[10.5px] text-muted-foreground">{hint}</span>
    </label>
  )
}
