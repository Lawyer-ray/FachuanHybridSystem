import { Check } from 'lucide-react'
import { DropdownMenuItem } from '@/components/ui/dropdown-menu'

/**
 * 单选项：左侧勾选位固定宽度，右侧「标签 + 一句后果」。
 *
 * 为什么把后果写出来：这几个选项都**直接影响费用与结果可信度**
 * （补版面按页计费、锁定平台失败即失败），只写一个名词用户无从判断。
 * 勾选位用固定宽度而不是「标签后面跟 ✓」，是为了让两行文案左对齐。
 *
 * 多选的兄弟项见 `CheckItem`（两者视觉刻意一致）。
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
