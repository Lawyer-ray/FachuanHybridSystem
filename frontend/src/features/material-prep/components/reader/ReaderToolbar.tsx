import { Loader2, Minus, MoreHorizontal, Plus, Columns3 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { PBTN, PBTN_ON } from './ui'
import { cn } from '@/lib/utils'

/** 预处理工具条（原型 rd-pre）。
 *
 *  只留高频动作：选页 / 追加材料 / 缩放（桌面）/ 列数（桌面）/ 自动分段 / ⋯。
 *  进度在顶栏副标题，「完成拆分与归类」是空动作已删（归案才是收口），
 *  低频且有破坏性的「恢复初始分段」和键位说明收进 ⋯。手机上缩放靠双指捏合、
 *  列数恒 1，都隐藏；布局规则在 material-prep.css 的 .mp-rd-toolbar。 */
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
}) {
  return (
    // 外层只负责边框底色与手机端右缘渐变（渐变得挂在不滚动的层上，否则跟着内容一起滚走）
    <div className="relative flex-none border-b border-border bg-card max-[760px]:after:pointer-events-none max-[760px]:after:absolute max-[760px]:after:inset-y-0 max-[760px]:after:right-0 max-[760px]:after:w-8 max-[760px]:after:bg-gradient-to-l max-[760px]:after:from-card max-[760px]:after:to-transparent">
      <div className="mp-rd-toolbar text-[12.5px]">
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

        {/* 缩放三件套：桌面专用。手机靠系统双指捏合（index.html 的 viewport 未禁缩放），
            按钮只是占横向空间；放大后的清晰度由 PdfPageView 的 DPR 位图兜着 */}
        <button type="button" onClick={onZoomOut} title="缩小画布" aria-label="缩小画布" className={cn(PBTN, 'w-[30px] justify-center px-0 max-[760px]:hidden')}>
          <Minus className="h-3.5 w-3.5" />
        </button>
        <button type="button" onClick={onZoomReset} title="点击回到 100%" className={cn(PBTN, 'min-w-[52px] justify-center px-[8px] tabular-nums max-[760px]:hidden')}>
          {zoomVal}%
        </button>
        <button type="button" onClick={onZoomIn} title="放大画布" aria-label="放大画布" className={cn(PBTN, 'w-[30px] justify-center px-0 max-[760px]:hidden')}>
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

        {/* ⋯：低频 + 说明性内容。恢复初始分段会把拆分归位到「每源文件一份」，值得隔一层防误触 */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" aria-label="更多操作" title="更多操作" className={cn(PBTN, 'w-[30px] justify-center px-0')}>
              <MoreHorizontal className="h-3.5 w-3.5" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[220px]">
            <DropdownMenuItem onSelect={onResetSegments}>恢复初始分段</DropdownMenuItem>
            <DropdownMenuSeparator />
            {/* 键位说明不是动作，用 Label 行呈现 */}
            <DropdownMenuLabel className="text-[11px] font-normal leading-[1.9] text-muted-foreground">
              点页间虚线 = 切开
              <br />
              ⌘/Ctrl + 点页 = 选页 · ⌘/Ctrl + ⇧ 点 = 选区间
              <br />
              S = 合并选中页 · Esc = 逐级退出
            </DropdownMenuLabel>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  )
}
