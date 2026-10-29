import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * 阶段设计器的表单小件：字段壳（标签 + 说明）、文本输入、24×24 方钮、虚线小按钮。
 * 与 PhaseDesignPane 分开只为「单文件单一职责 + 规模红线」，没有独立行为。
 */

export function Field({ label, note, children }: { label: string; note?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[11.5px] font-[600] text-muted-foreground">
        {label}
        {note && <span className="ml-1.5 text-[11px] font-[400] text-muted-foreground/80">{note}</span>}
      </span>
      {children}
    </div>
  )
}

export function TextInput({ value, placeholder, onChange }: { value: string; placeholder: string; onChange: (v: string) => void }) {
  return (
    <input
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-[7px] border border-border bg-card px-2.5 py-2 text-[13px] text-foreground outline-none focus:border-input"
    />
  )
}

/** 层级/顺序/删除小方钮：24×24，箭头字形比文字省地方 */
export function IconBtn({
  label,
  danger,
  disabled,
  onClick,
  children,
}: {
  label: string
  danger?: boolean
  disabled?: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'size-6 shrink-0 cursor-pointer rounded-[6px] border border-border bg-card text-[11px] transition-colors',
        'hover:bg-secondary hover:text-foreground disabled:cursor-default disabled:opacity-35',
        danger ? 'text-muted-foreground hover:border-status-red/40 hover:text-status-red' : 'text-muted-foreground',
      )}
    >
      {children}
    </button>
  )
}

export function SmallDash({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex-1 cursor-pointer rounded-[7px] border border-dashed border-border px-2 py-1.5 text-center text-[11.5px] whitespace-nowrap text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground"
    >
      {children}
    </button>
  )
}
