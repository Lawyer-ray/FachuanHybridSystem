/** 选页汇总条（原型 selbar）：底部浮条，左侧计数、中间说明、右侧操作 */

import { RotateCcw, RotateCw } from 'lucide-react'

function RotateButton({
  label,
  onClick,
  children,
}: {
  label: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="grid h-6 w-6 place-items-center rounded-[5px] text-foreground/80 transition-colors hover:bg-secondary hover:text-foreground"
    >
      {children}
    </button>
  )
}
export function SelectionBar({
  count,
  cross,
  rotatedCount = 0,
  onClear,
  onApply,
  onRotate,
}: {
  count: number
  cross: boolean
  /** 所选页里已经转过正的有几页（0 时不给「重置」按钮） */
  rotatedCount?: number
  onClear: () => void
  onApply: () => void
  /** 批量人工转正：90 顺时针 / -90 逆时针 / 180 / 0 重置 */
  onRotate?: (deg: number) => void
}) {
  return (
    // 底栏已删，浮条贴底 16px；手机收到屏宽内并允许换行（四段内容一行放不下会横向溢出屏幕）
    <div className="fixed bottom-4 left-1/2 z-[60] flex -translate-x-1/2 items-center gap-3 rounded-xl border border-border bg-card px-4 py-2 shadow-2xl max-[760px]:w-[calc(100vw-16px)] max-[760px]:flex-wrap max-[760px]:justify-center max-[760px]:gap-x-3 max-[760px]:gap-y-1.5 max-[760px]:px-3">
      <span className="text-[13px] font-medium tabular-nums">{count} 页</span>
      <span className="text-[12px] text-muted-foreground">
        {cross ? '来自多份材料，将合并为一份' : '来自同一份，将独立成一份新材料'}
      </span>

      {/* 批量转正：倒着送纸扫出来的几十页在这里一次转回来，不用逐页点 */}
      {onRotate && (
        <span className="flex items-center gap-0.5 rounded-md border border-border px-1 py-0.5">
          <span className="px-1 text-[11px] text-muted-foreground">
            转正{rotatedCount > 0 ? `（已转 ${rotatedCount}）` : ''}
          </span>
          <RotateButton label="所选页逆时针旋转 90°" onClick={() => onRotate(-90)}>
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />
          </RotateButton>
          <RotateButton label="所选页顺时针旋转 90°" onClick={() => onRotate(90)}>
            <RotateCw className="h-3.5 w-3.5" aria-hidden />
          </RotateButton>
          <RotateButton label="所选页旋转 180°" onClick={() => onRotate(180)}>
            <span className="text-[10.5px] leading-none font-medium">180°</span>
          </RotateButton>
          {rotatedCount > 0 && (
            <RotateButton label="所选页方向重置" onClick={() => onRotate(0)}>
              <span className="text-[10.5px] leading-none">0°</span>
            </RotateButton>
          )}
        </span>
      )}
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
