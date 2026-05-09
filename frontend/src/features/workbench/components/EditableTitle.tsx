/** 可编辑标题组件 */

import { useState, useRef, useEffect } from 'react'
import { Pencil } from 'lucide-react'
import { Input } from '@/components/ui/input'

interface EditableTitleProps {
  title: string
  editable: boolean
  onSave: (title: string) => void
}

export function EditableTitle({ title, editable, onSave }: EditableTitleProps) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(title)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!editing) setValue(title)
  }, [title, editing])

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const handleSave = () => {
    const trimmed = value.trim()
    if (trimmed && trimmed !== title) {
      onSave(trimmed)
    }
    setEditing(false)
  }

  if (!editable) {
    return <h2 className="text-sm font-medium">{title}</h2>
  }

  if (editing) {
    return (
      <Input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={handleSave}
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSave()
          if (e.key === 'Escape') { setValue(title); setEditing(false) }
        }}
        className="h-7 text-sm font-medium"
      />
    )
  }

  return (
    <div className="group flex items-center gap-1.5">
      <h2 className="text-sm font-medium truncate">{title}</h2>
      <button
        onClick={() => setEditing(true)}
        className="hidden text-muted-foreground hover:text-foreground group-hover:block"
      >
        <Pencil className="size-3" />
      </button>
    </div>
  )
}
