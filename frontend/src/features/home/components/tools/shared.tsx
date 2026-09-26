import type { ReactNode } from 'react'

/** 共用的转圈图标（四张卡 busy 态都用它） */
export function Spinner() {
  return (
    <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity=".25" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

/** 工具卡外壳：图标 + 标题 + 后端端点注释 + 内容区 */
export function ToolShell({
  icon,
  title,
  endpoint,
  children,
}: {
  icon: ReactNode
  title: string
  endpoint: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col rounded-[12px] border border-border bg-secondary/30 p-[13px]">
      <div className="mb-[11px] flex items-center gap-2.5">
        <div className="flex h-7 w-7 flex-none items-center justify-center rounded-[8px] border border-border bg-card text-secondary-foreground">
          {icon}
        </div>
        <div className="min-w-0">
          <div className="text-[12.5px] leading-[1.2] font-semibold">{title}</div>
          <div className="mt-[2px] truncate font-mono text-[9px] text-muted-foreground" title={endpoint}>
            {endpoint}
          </div>
        </div>
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
  onPick,
}: {
  label: string
  hint: string
  accept: string
  multiple?: boolean
  onPick: (files: File[]) => void
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded-[8px] border border-dashed border-input bg-secondary/30 px-[9px] py-[6px] transition-colors hover:border-ring/40 hover:bg-card">
      <input
        type="file"
        accept={accept}
        multiple={multiple}
        className="hidden"
        onChange={(e) => onPick(Array.from(e.target.files ?? []))}
      />
      <span className="text-[11px] font-medium whitespace-nowrap text-secondary-foreground">{label}</span>
      <span className="truncate text-[10.5px] text-muted-foreground">{hint}</span>
    </label>
  )
}
