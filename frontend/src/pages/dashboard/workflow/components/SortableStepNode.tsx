/**
 * 可排序步骤节点 — 封装 @dnd-kit 的 useSortable
 */
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { StepNodeCard } from './StepNodeCard'
import type { StepNode } from '@/features/workflow/types'

interface SortableStepNodeProps {
  step: StepNode
  isSelected: boolean
  onSelect: () => void
  onRemove: () => void
  onDuplicate: () => void
  stepIndex: number
}

export function SortableStepNode({
  step,
  isSelected,
  onSelect,
  onRemove,
  onDuplicate,
  stepIndex,
}: SortableStepNodeProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: step.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <div ref={setNodeRef} style={style} {...attributes}>
      <StepNodeCard
        step={step}
        isSelected={isSelected}
        onSelect={onSelect}
        onRemove={onRemove}
        onDuplicate={onDuplicate}
        stepIndex={stepIndex}
        isDragging={isDragging}
        dragHandleProps={listeners}
      />
    </div>
  )
}
