/** 选页汇总条（原型 selbar）：底部浮条，左侧计数、中间说明、右侧操作 */
export function SelectionBar({
  count,
  cross,
  onClear,
  onApply,
}: {
  count: number
  cross: boolean
  onClear: () => void
  onApply: () => void
}) {
  return (
    <div className="fixed bottom-[62px] left-1/2 z-[60] flex -translate-x-1/2 items-center gap-3 rounded-xl border border-border bg-card px-4 py-2 shadow-2xl">
      <span className="text-[13px] font-medium tabular-nums">{count} 页</span>
      <span className="text-[12px] text-muted-foreground">
        {cross ? '来自多份材料，将合并为一份' : '来自同一份，将独立成一页新材料'}
      </span>
      <button type="button" onClick={onClear} className="text-[12px] text-secondary-foreground hover:underline">
        取消选择
      </button>
      <button
        type="button"
        onClick={onApply}
        className="rounded-md bg-zinc-900 px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-zinc-700"
      >
        {cross ? '合并为一份材料' : '独立成一份材料'}
      </button>
    </div>
  )
}
