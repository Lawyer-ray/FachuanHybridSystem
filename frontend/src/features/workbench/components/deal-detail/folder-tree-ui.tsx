import { useState } from 'react'

/** 行内新建 / 重命名输入框：Enter 确认、Esc 取消、失焦取消（无歧义动作不做弹窗） */
export function EntryInput({
  initial = '',
  placeholder,
  onConfirm,
  onCancel,
}: {
  initial?: string
  placeholder: string
  onConfirm: (name: string) => void
  onCancel: () => void
}) {
  const [v, setV] = useState(initial)
  return (
    <input
      autoFocus
      value={v}
      placeholder={placeholder}
      onChange={(e) => setV(e.target.value)}
      onBlur={onCancel}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          const name = v.trim()
          if (name) onConfirm(name)
          else onCancel()
        } else if (e.key === 'Escape') onCancel()
      }}
      onClick={(e) => e.stopPropagation()}
      className="w-full rounded-[6px] border border-input bg-background px-2 py-1 text-[12.5px] text-secondary-foreground outline-none focus:border-foreground/40"
    />
  )
}
