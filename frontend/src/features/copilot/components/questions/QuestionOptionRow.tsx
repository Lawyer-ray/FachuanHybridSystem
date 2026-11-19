/**
 * 提问卡的一个选项行。
 *
 * 从 `QuestionCard` 拆出（该文件已接近 200 行的理想上限）：这里是唯一需要
 * `role=radio/checkbox` + `aria-checked` 的地方，读屏语义与点选样式聚在一处，
 * 卡片本体只负责编排。
 */

import type { QuestionItem } from '../../types'

export function QuestionOptionRow({
  item,
  label,
  description,
  selected,
  disabled,
  onClick,
}: {
  item: QuestionItem
  label: string
  description: string
  selected: boolean
  disabled: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      role={item.allowMultiple ? 'checkbox' : 'radio'}
      aria-checked={selected}
      disabled={disabled}
      onClick={onClick}
      className={`w-full rounded-[8px] border px-2.5 py-2 text-left transition-colors disabled:opacity-60 ${
        selected ? 'border-primary/60 bg-primary/10' : 'border-border hover:bg-secondary'
      }`}
    >
      <span className="block text-[13px] font-medium">{label}</span>
      {description && (
        <span className="mt-0.5 block text-[11px] leading-relaxed text-muted-foreground">
          {description}
        </span>
      )}
    </button>
  )
}
