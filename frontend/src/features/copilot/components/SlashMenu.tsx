/**
 * `/` 命令菜单浮层（受控组件：状态与键盘在 use-slash-menu / Composer）。
 *
 * listbox/option 语义 + 鼠标悬停同步选中；禁用项（无会话时的 compact）
 * 可见但置灰并给出原因小字。风格与 Composer 同一中性灰阶（无 emoji）。
 */

import { Archive } from 'lucide-react'
import type { SlashMenuItem } from '../types'

export interface SlashMenuProps {
  items: SlashMenuItem[]
  selectedIndex: number
  onHover: (index: number) => void
  onSelect: (item: SlashMenuItem) => void
}

export function SlashMenu({ items, selectedIndex, onHover, onSelect }: SlashMenuProps) {
  if (items.length === 0) {
    return (
      <div
        className="absolute bottom-full left-0 right-0 mb-1.5 rounded-[10px] border border-border bg-popover p-2.5 text-[12px] text-muted-foreground shadow-md"
        role="listbox"
        aria-label="命令菜单"
      >
        无匹配命令
      </div>
    )
  }
  return (
    <div
      className="absolute bottom-full left-0 right-0 mb-1.5 max-h-64 overflow-y-auto rounded-[10px] border border-border bg-popover py-1 shadow-md"
      role="listbox"
      aria-label="命令菜单"
    >
      {items.map((item, i) => (
        <button
          key={item.key}
          type="button"
          role="option"
          aria-selected={i === selectedIndex}
          aria-disabled={item.disabled}
          className={`flex w-full items-start gap-2 px-2.5 py-1.5 text-left transition-colors ${
            item.disabled ? 'cursor-not-allowed opacity-45' : 'hover:bg-secondary/60'
          } ${i === selectedIndex && !item.disabled ? 'bg-secondary/60' : ''}`}
          onMouseEnter={() => onHover(i)}
          onClick={() => onSelect(item)}
        >
          <span className="mt-0.5 flex h-4 w-4 flex-none items-center justify-center text-muted-foreground">
            {item.kind === 'command' ? <Archive className="h-3.5 w-3.5" /> : null}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12.5px] text-foreground">
              {item.kind === 'skill' ? `/skill:${item.label}` : `/${item.id}`}
            </span>
            <span className="block truncate text-[11px] text-muted-foreground">
              {item.disabled && item.disabledHint ? item.disabledHint : item.description}
            </span>
          </span>
        </button>
      ))}
    </div>
  )
}
