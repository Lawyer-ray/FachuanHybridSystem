import { Loader2, Minus, MoreHorizontal, Plus, Columns3 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { PBTN, PBTN_ON } from './ui'
import { cn } from '@/lib/utils'

/**
 * 阅读器工具组。
 *
 * `inline`（≥1100px）时把按钮组直接嵌进顶栏那一行（不自带边框 / 高度）；
 * 否则渲染为顶栏下方的独立一行：桌面 min-h 可换行，手机（≤760px）单行横向滚动，
 * 右缘渐变提示还有更多（布局规则在 material-prep.css 的 .mp-rd-toolbar）。
 *
 * 手机上只留触屏真会用到的：材料 / 信息 / 选页 / 追加材料 / 自动分段 / ⋯——
 * 缩放靠系统双指捏合，列数恒 1，归案在顶栏。
 */
export function ReaderToolbar({
  narrow,
  railOpen,
  metaOpen,
  onToggleRail,
  onToggleMeta,
  selMode,
  onToggleSelMode,
  onAddFiles,
  zoomVal,
  onZoomIn,
  onZoomOut,
  onZoomReset,
  cols,
  colsDisabled,
  onChangeCols,
  onResetSegments,
  onAutoSplit,
  autoSplitRunning,
  autoSplitProgress,
  inline = false,
}: {
  narrow: boolean
  railOpen: boolean
  metaOpen: boolean
  onToggleRail: () => void
  onToggleMeta: () => void
  selMode: boolean
  onToggleSelMode: () => void
  onAddFiles: () => void
  zoomVal: number
  onZoomIn: () => void
  onZoomOut: () => void
  onZoomReset: () => void
  cols: number
  colsDisabled: boolean
  onChangeCols: () => void
  onResetSegments: () => void
  onAutoSplit: () => void
  autoSplitRunning: boolean
  autoSplitProgress: string
  /** 嵌入顶栏行（≥1100px）：只输出按钮组，不自带容器 */
  inline?: boolean
}) {
  const tools = (
    <>
      {narrow ? (
        <>
          <button type="button" onClick={onToggleRail} className={cn(PBTN, railOpen && PBTN_ON)}>
            材料
          </button>
          <button type="button" onClick={onToggleMeta} className={cn(PBTN, metaOpen && PBTN_ON)}>
            信息
          </button>
        </>
      ) : null}

      <span className="flex-1" />

      <button type="button" onClick={onToggleSelMode} title="选页模式：点一张选中，⇧+点 选区间（或随时 ⌘/Ctrl+点）" className={cn(PBTN, selMode && PBTN_ON)}>
        选页
      </button>
      <button type="button" onClick={onAddFiles} title="点这里选文件，或把文件直接拖到这儿" className={PBTN}>
        <Plus className="h-3.5 w-3.5" />
        追加材料
      </button>

      <span className="h-4 w-px flex-none bg-border" />

      {/* 缩放三件套：桌面专用。手机靠系统双指捏合（viewport 未禁缩放），
          按钮只是占横向空间；放大后的清晰度由 PdfPageView 的 DPR 位图兜着 */}
      <button type="button" onClick={onZoomOut} title="缩小画布（⌘/Ctrl + 滚轮）" aria-label="缩小画布" className={cn(PBTN, 'w-[30px] justify-center px-0 max-[760px]:hidden')}>
        <Minus className="h-3.5 w-3.5" />
      </button>
      <button type="button" onClick={onZoomReset} title="点击回到 100%" className={cn(PBTN, 'min-w-[52px] justify-center px-[8px] tabular-nums max-[760px]:hidden')}>
        {zoomVal}%
      </button>
      <button type="button" onClick={onZoomIn} title="放大画布（⌘/Ctrl + 滚轮）" aria-label="放大画布" className={cn(PBTN, 'w-[30px] justify-center px-0 max-[760px]:hidden')}>
        <Plus className="h-3.5 w-3.5" />
      </button>

      {/* 列数：点一下在 1 列和当前窗口上限间切换；手机永远只够 1 列，不占位 */}
      <button
        type="button"
        onClick={onChangeCols}
        disabled={colsDisabled}
        title={`并排列数：当前 ${cols} 列${colsDisabled ? '（窗口还不够宽，并排至少每列 360px）' : '，点一下切换'}`}
        aria-label={`并排列数：当前 ${cols} 列`}
        className={cn(PBTN, 'w-[30px] justify-center px-0 disabled:cursor-not-allowed disabled:opacity-40 max-[760px]:hidden')}
      >
        <Columns3 className="h-3.5 w-3.5" />
      </button>

      <span className="h-4 w-px flex-none bg-border max-[760px]:hidden" />

      <Button size="sm" variant="outline" className="flex-none" onClick={onAutoSplit} disabled={autoSplitRunning} title={autoSplitProgress || '调用 MinerU / Textin 逐页识别并生成分段建议'}>
        {autoSplitRunning && <Loader2 className="h-4 w-4 animate-spin" />}
        {autoSplitRunning ? autoSplitProgress || '识别中…' : '自动分段'}
      </Button>

      {/* ⋯：低频 + 有破坏性的「恢复初始分段」收进来防误触 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button type="button" aria-label="更多操作（恢复初始分段）" title="更多操作：恢复初始分段" className={cn(PBTN, 'w-[30px] justify-center px-0')}>
            <MoreHorizontal className="h-3.5 w-3.5" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[200px]">
          <DropdownMenuItem onSelect={onResetSegments}>恢复初始分段</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  )

  if (inline) {
    // 嵌入顶栏：只输出按钮组，justify-end 让它们靠向右侧的 不接/归案
    return <div className="hidden min-[1100px]:flex min-w-0 flex-1 items-center justify-end gap-2 text-[12.5px]">{tools}</div>
  }

  return (
    // 外层只负责边框底色与手机端右缘渐变（渐变得挂在不滚动的层上，否则跟着内容一起滚走）
    <div className="relative flex-none border-b border-border bg-card min-[1100px]:hidden max-[760px]:after:pointer-events-none max-[760px]:after:absolute max-[760px]:after:inset-y-0 max-[760px]:after:right-0 max-[760px]:after:w-8 max-[760px]:after:bg-gradient-to-l max-[760px]:after:from-card max-[760px]:after:to-transparent">
      <div className="mp-rd-toolbar text-[12.5px]">{tools}</div>
    </div>
  )
}
