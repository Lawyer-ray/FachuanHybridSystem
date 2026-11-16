import { Check } from 'lucide-react'
import { DropdownMenuItem } from '@/components/ui/dropdown-menu'

/**
 * 阅读器设置菜单里的两种设置项（单选 / 多选）。
 *
 * 从 ReaderToolbar 拆出：工具条本体（按钮组 + 视图菜单）与「自动分段设置」菜单
 * 是两个关注点，合在一个文件里已顶过规模软红线。两种项视觉刻意一致——
 * 同一个菜单里版面策略是单选、解析平台是多选，勾选位长得不一样会让人以为其中一处坏了。
 */

/**
 * 单选项：左侧勾选位固定宽度，右侧「标签 + 一句后果」。
 *
 * 为什么把后果写出来：这几个选项都**直接影响费用与结果可信度**
 * （补版面按页计费、锁定平台失败即失败），只写一个名词用户无从判断。
 * 勾选位用固定宽度而不是「标签后面跟 ✓」，是为了让两行文案左对齐。
 */
export function PickItem({
  checked,
  onSelect,
  label,
  hint,
}: {
  checked: boolean
  onSelect: () => void
  label: string
  hint: string
}) {
  return (
    <DropdownMenuItem onSelect={onSelect} className="items-start gap-2 py-1.5">
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

/**
 * 多选项：勾选框 + 左侧标签 + 一句后果。
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
