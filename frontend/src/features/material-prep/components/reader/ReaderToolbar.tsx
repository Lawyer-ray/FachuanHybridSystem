import { CheckCircle2, Loader2, Minus, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PBTN, PBTN_ON } from './ui'
import { cn } from '@/lib/utils'

/** 预处理工具条（原型 rd-pre）：左进度、右操作，统一 pbtn 描边样式。
 *
 *  布局规则在 material-prep.css 的 .mp-rd-toolbar：桌面 min-h 允许换行可见，
 *  手机（≤760px）单行横向滚动。手机上只留触屏真会用到的：材料 / 信息 / 选页 /
 *  追加材料 / 云端识别 / 恢复分段——缩放靠系统双指捏合（viewport 未禁缩放），
 *  列数恒 1，「完成」在底栏拇指区（KeyHintsBar）。 */
export function ReaderToolbar({
  narrow,
  railOpen,
  metaOpen,
  onToggleRail,
  onToggleMeta,
  progressText,
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
  onComplete,
}: {
  narrow: boolean
  railOpen: boolean
  metaOpen: boolean
  onToggleRail: () => void
  onToggleMeta: () => void
  progressText: string
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
  onComplete: () => void
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
        {/* 进度徽章 + 文案：手机上文案早被 sm:inline 藏掉，孤零零一个「进度」徽章没有信息量，一并藏 */}
        <span className="flex-none rounded-[4px] bg-secondary px-[7px] py-[2px] text-[10px] font-bold uppercase tracking-wide text-secondary-foreground max-[760px]:hidden">
          进度
        </span>
        <span className="hidden text-[12px] text-secondary-foreground sm:inline max-[760px]:hidden">{progressText}</span>

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

        {/* 列数：手机永远只够 1 列（每列至少 360px），按钮恒禁用，不占横向空间 */}
        <button
          type="button"
          onClick={onChangeCols}
          disabled={colsDisabled}
          title={colsDisabled ? '窗口还不够宽 —— 并排至少要有每列 360px' : '并排列数：点一下在 1 列和多列之间切换'}
          className={cn(PBTN, 'tabular-nums disabled:cursor-not-allowed disabled:opacity-40 max-[760px]:hidden')}
        >
          列数：{cols}
        </button>

        {/* 这条分隔线跟缩放 / 列数一起藏：否则手机上会和前一条贴成双线 */}
        <span className="h-4 w-px flex-none bg-border max-[760px]:hidden" />

        <Button size="sm" variant="outline" className="flex-none" onClick={onAutoSplit} disabled={autoSplitRunning} title={autoSplitProgress || '调用 MinerU / Textin 逐页识别并生成分段建议'}>
          {autoSplitRunning && <Loader2 className="h-4 w-4 animate-spin" />}
          {autoSplitRunning ? autoSplitProgress || '识别中…' : '云端内容识别'}
        </Button>
        <button type="button" onClick={onResetSegments} className={PBTN}>
          恢复初始分段
        </button>
        {/* 完成：手机挪到底栏（拇指区 + 不用横滚才找得到），见 KeyHintsBar */}
        <Button size="sm" className="ml-1 flex-none max-[760px]:hidden" onClick={onComplete}>
          <CheckCircle2 className="h-4 w-4" />
          完成拆分与归类
        </Button>
      </div>
    </div>
  )
}
