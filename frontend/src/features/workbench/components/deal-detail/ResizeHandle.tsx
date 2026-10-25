import { cn } from '@/lib/utils'

/**
 * 分栏拖拽手柄。
 *
 * 视觉上是一条 1px 竖线，但**命中区做到 9px 宽**——1px 的线要精确点到很难，
 * 而视觉上太宽的抓手又脏。做法是外层透明宽区负责接收指针，内层细线负责显示，
 * 悬浮/拖拽时内层加粗并变色，给出可拖的反馈。
 *
 * 键盘也能调：role="separator" + 方向键，避免「只有鼠标能用」。
 */
export function ResizeHandle({
  dragging,
  onPointerDown,
  onKeyAdjust,
  label = '调整宽度',
}: {
  dragging: boolean
  onPointerDown: (e: React.PointerEvent) => void
  /** 键盘调整：传 ±1 表示放大/缩小一档 */
  onKeyAdjust?: (direction: 1 | -1) => void
  label?: string
}) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft') {
          e.preventDefault()
          onKeyAdjust?.(-1)
        } else if (e.key === 'ArrowRight') {
          e.preventDefault()
          onKeyAdjust?.(1)
        }
      }}
      className={cn(
        // -mx：把 9px 命中区的一半探进两侧栏，否则它会把两栏推开
        'group relative -mx-[4px] w-[9px] flex-none cursor-col-resize select-none',
        'focus:outline-none',
      )}
      title="拖动调整宽度（也可用 ← → 键）"
    >
      <span
        className={cn(
          'absolute inset-y-0 left-1/2 w-px -translate-x-1/2 transition-all',
          // 常态几乎看不见，悬浮时变粗变深——不抢版面，但能找到
          dragging
            ? 'w-[3px] bg-foreground'
            : 'bg-transparent group-hover:w-[3px] group-hover:bg-border group-focus-visible:w-[3px] group-focus-visible:bg-foreground',
        )}
      />
    </div>
  )
}
