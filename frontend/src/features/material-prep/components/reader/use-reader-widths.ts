import { cn } from '@/lib/utils'
import { maxColsAllowed } from './layout'

/**
 * 阅读器列宽与抽屉样式派生：
 *   - maxCols：当前容器宽度下最多能并排几列
 *   - effCols：用户选择 cols 与 maxCols 的较小值
 *   - railWrapCls / metaWrapCls：左右抽屉在窄屏（fixed 抽屉）与宽屏（inline）两套 class
 * 列数口径统一走 layout.ts，和 Flow 内部同一套数学。
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
  const effCols = Math.max(1, Math.min(cols, maxCols))

  const railWrapCls = narrow
    ? cn(
        'fixed inset-y-0 left-0 z-40 w-[268px] overflow-y-auto border-r border-border bg-card transition-transform duration-300',
        railOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full',
      )
    : 'h-full flex-none'
  const metaWrapCls = narrow
    ? cn(
        'fixed inset-y-0 right-0 z-40 w-[296px] overflow-y-auto border-l border-border bg-card transition-transform duration-300',
        metaOpen ? 'translate-x-0 shadow-2xl' : 'translate-x-full',
      )
    : 'h-full flex-none'

  return { maxCols, effCols, railWrapCls, metaWrapCls }
}
