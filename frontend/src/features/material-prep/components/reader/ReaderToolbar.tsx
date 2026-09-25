import { CheckCircle2, Loader2, Minus, Plus, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PBTN, PBTN_ON } from './ui'
import { cn } from '@/lib/utils'

/** 预处理工具条（原型 rd-pre）：左进度、右操作，统一 pbtn 描边样式 */
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
    <div className="flex h-[56px] flex-none flex-wrap items-center gap-2 border-b border-border bg-card px-4 text-[12.5px]">
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
      <span className="flex-none rounded-[4px] bg-secondary px-[7px] py-[2px] text-[10px] font-bold uppercase tracking-wide text-secondary-foreground">
        进度
      </span>
      <span className="hidden text-[12px] text-secondary-foreground sm:inline">{progressText}</span>

      <span className="flex-1" />

      <button type="button" onClick={onToggleSelMode} title="选页模式：点一张选中，⇧+点 选区间（或随时 ⌘/Ctrl+点）" className={cn(PBTN, selMode && PBTN_ON)}>
        选页
      </button>
      <button type="button" onClick={onAddFiles} title="点这里选文件，或把文件直接拖到这儿" className={PBTN}>
        <Plus className="h-3.5 w-3.5" />
        追加材料
      </button>

      <span className="h-4 w-px bg-border" />

      <button type="button" onClick={onZoomOut} title="缩小画布" className={cn(PBTN, 'w-[30px] justify-center px-0')}>
        <Minus className="h-3.5 w-3.5" />
      </button>
      <button type="button" onClick={onZoomReset} title="点击回到 100%" className={cn(PBTN, 'min-w-[52px] justify-center px-[8px] tabular-nums')}>
        {zoomVal}%
      </button>
      <button type="button" onClick={onZoomIn} title="放大画布" className={cn(PBTN, 'w-[30px] justify-center px-0')}>
        <Plus className="h-3.5 w-3.5" />
      </button>

      <button
        type="button"
        onClick={onChangeCols}
        disabled={colsDisabled}
        title={colsDisabled ? '窗口还不够宽 —— 并排至少要有每列 360px' : '并排列数：点一下在 1 列和多列之间切换'}
        className={cn(PBTN, 'tabular-nums disabled:cursor-not-allowed disabled:opacity-40')}
      >
        列数：{cols}
      </button>

      <span className="h-4 w-px bg-border" />

      <Button size="sm" variant="outline" onClick={onAutoSplit} disabled={autoSplitRunning} title={autoSplitProgress || '调用 MinerU / Textin 逐页识别并生成分段建议'}>
        {autoSplitRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
        {autoSplitRunning ? autoSplitProgress || '识别中…' : '云端内容识别'}
      </Button>
      <button type="button" onClick={onResetSegments} className={PBTN}>
        恢复初始分段
      </button>
      <Button size="sm" className="ml-1" onClick={onComplete}>
        <CheckCircle2 className="h-4 w-4" />
        完成拆分与归类
      </Button>
    </div>
  )
}
