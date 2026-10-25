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
        // 命中区 10px、自带左右内边距，在 flex 行里是**真实占位**的一块。
        // 之前用 -mx-[4px] 让它视觉上嵌进两侧栏，结果左侧是 flex-1 的邻居，
        // 绘制层叠在上（DOM 在前），那 4px 被盖住 → 点不到、拖不动。
        // 现在不叠负边距，宽度算在布局里，两栏之间自然形成 10px 的呼吸区。
        'group relative z-10 w-[10px] flex-none cursor-col-resize select-none',
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
