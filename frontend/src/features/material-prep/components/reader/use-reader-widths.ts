import { cn } from '@/lib/utils'
import { effectiveCols, maxColsAllowed } from './layout'
import { META_WIDE_DEFAULT } from './use-meta-width'
import { RAIL_WIDE_DEFAULT } from './use-rail-width'

/**
 * 阅读器列宽与抽屉样式派生：
 *   - maxCols：当前容器宽度下最多能并排几列
 *   - effCols：用户选择 cols 与 maxCols 的较小值
 *   - railWrapCls / metaWrapCls：左右抽屉在窄屏（absolute 覆盖抽屉）与宽屏（inline）两套 class
 *   - railWrapStyle / metaWrapStyle：窄屏抽屉的**宽度**（宽屏为 undefined，宽度由拖拽控制）
 * 列数口径统一走 layout.ts 的 effectiveCols，和 Flow 内部同一套数学。
 *
 * 宽度为什么走 inline style 而不是 `w-[268px]` 这种 class：抽屉宽度与宽屏默认宽是**同
 * 一个数**（`RAIL_WIDE_DEFAULT` / `META_WIDE_DEFAULT`），写两套字面量必然漂移——
 * 改常量时抽屉不跟着变，反之亦然。inline style 能直接引用常量，class 做不到
 * （Tailwind 只认源码里的字面量，模板拼出来的 `w-[${n}px]` 不会被生成）。
 * 抽屉用 absolute（相对三栏主体行）而非 fixed：阅读器右缘会为并排 AI 助手
 * 收进来，fixed 定位到视口会把右抽屉画到助手底下去。
 */
export function useReaderWidths(params: {
  cols: number
  flowWrapW: number
  narrow: boolean
  railOpen: boolean
  metaOpen: boolean
}) {
  const { cols, flowWrapW, narrow, railOpen, metaOpen } = params

  const maxCols = maxColsAllowed(flowWrapW)
  const effCols = effectiveCols(cols, flowWrapW)

  const railWrapCls = narrow
    ? cn(
        'absolute inset-y-0 left-0 z-40 overflow-y-auto border-r border-border bg-card transition-transform duration-300',
        railOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full',
      )
    : 'h-full flex-none'
  const metaWrapCls = narrow
    ? cn(
        'absolute inset-y-0 right-0 z-40 overflow-y-auto border-l border-border bg-card transition-transform duration-300',
        metaOpen ? 'translate-x-0 shadow-2xl' : 'translate-x-full',
      )
    : 'h-full flex-none'
  // 窄屏浮层宽度：与宽屏默认宽同一个常量（见文件头）。宽屏不设宽度——
  // 那里宽度由 Rail/MetaPanel 的拖拽手柄控制
  const railWrapStyle: React.CSSProperties | undefined = narrow ? { width: RAIL_WIDE_DEFAULT } : undefined
  const metaWrapStyle: React.CSSProperties | undefined = narrow ? { width: META_WIDE_DEFAULT } : undefined

  return { maxCols, effCols, railWrapCls, metaWrapCls, railWrapStyle, metaWrapStyle }
}
