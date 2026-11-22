import { Check } from 'lucide-react'
import { DropdownMenuItem } from '@/components/ui/dropdown-menu'

/**
 * 多选项：勾选框 + 左侧标签 + 一句后果。
 *
 * 与 `PickItem` 视觉刻意一致——同一个菜单里版面策略是单选、解析平台是多选，
 * 勾选位长得不一样会让人以为其中一处坏了。差别只在语义：这里是
 * `menuitemcheckbox` + `aria-checked`。
 *
 * `onSelect` 里 `preventDefault()` 是因为 Radix 的菜单项默认「选中即关菜单」：
 * 多选要连续勾几个，不能一勾就收起来。
 */
export function CheckItem({
  checked,
  onToggle,
  label,
  hint,
}: {
  checked: boolean
  onToggle: () => void
  label: string
  hint: string
}) {
  return (
    <DropdownMenuItem
      role="menuitemcheckbox"
      aria-checked={checked}
      onSelect={(e) => {
        e.preventDefault()
        onToggle()
      }}
      className="items-start gap-2 py-1.5"
    >
      <span className="mt-[2px] flex h-3.5 w-3.5 flex-none items-center justify-center">
        {checked && <Check className="h-3.5 w-3.5" />}
      </span>
      <span className="min-w-0">
        <span className="block text-[12.5px] leading-4">{label}</span>
        <span className="block text-[11px] leading-4 text-muted-foreground">{hint}</span>
      </span>
    </DropdownMenuItem>
  )
}
