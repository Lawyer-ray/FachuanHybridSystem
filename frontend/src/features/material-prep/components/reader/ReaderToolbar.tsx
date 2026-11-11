import { Check, ChevronDown, Loader2, Minus, Plus, Columns3 } from 'lucide-react'
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
  layoutMode,
  onLayoutModeChange,
  cloudBackend,
  onCloudBackendChange,
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
  /** 版面策略（补版面 = 电子页也上云端拿坐标，按页计费） */
  layoutMode: 'fast_text' | 'layout'
  onLayoutModeChange: (m: 'fast_text' | 'layout') => void
  /** 云端平台偏好：auto=优先+容灾；锁定=只用它，失败不降级 */
  cloudBackend: 'auto' | 'mineru' | 'textin'
  onCloudBackendChange: (b: 'auto' | 'mineru' | 'textin') => void
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

      {/* 自动分段：**主按钮直接执行**，右侧小三角才开设置。
          以前设置散在 ⋯ 菜单里，和「恢复初始分段」这种破坏性操作挤在同一串
          列表里，既难找也不知道它们会改变"下次识别"的行为。改成 split button：
          点主体 = 立刻跑，点箭头 = 先调参数，语义与位置都对上了。 */}
      <div className="flex flex-none items-stretch">
        <Button
          size="sm"
          variant="outline"
          className="rounded-r-none border-r-0"
          onClick={onAutoSplit}
          disabled={autoSplitRunning}
          title={autoSplitProgress || autoSplitTitle(layoutMode, cloudBackend)}
        >
          {autoSplitRunning && <Loader2 className="h-4 w-4 animate-spin" />}
          {autoSplitRunning ? autoSplitProgress || '识别中…' : '自动分段'}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label="自动分段设置"
              title="自动分段设置：版面策略 / 解析平台"
              disabled={autoSplitRunning}
              className="flex w-[26px] items-center justify-center rounded-r-[6px] border border-l-0 border-input text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[260px]">
            <DropdownMenuLabel className="text-[11px] font-normal text-muted-foreground">
              版面策略
            </DropdownMenuLabel>
            <PickItem
              checked={layoutMode === 'fast_text'}
              onSelect={() => onLayoutModeChange('fast_text')}
              label="仅文本层"
              hint="电子版不上云 · 最快 · 无坐标"
            />
            <PickItem
              checked={layoutMode === 'layout'}
              onSelect={() => onLayoutModeChange('layout')}
              label="补版面"
              hint="电子页也上云 · 可定位 · 按页计费"
            />

            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-[11px] font-normal text-muted-foreground">
              解析平台
            </DropdownMenuLabel>
            <PickItem
              checked={cloudBackend === 'auto'}
              onSelect={() => onCloudBackendChange('auto')}
              label="自动"
              hint="首选失败自动切下一个"
            />
            <PickItem
              checked={cloudBackend === 'mineru'}
              onSelect={() => onCloudBackendChange('mineru')}
              label="仅 MinerU"
              hint="锁定 · 失败不降级"
            />
            <PickItem
              checked={cloudBackend === 'textin'}
              onSelect={() => onCloudBackendChange('textin')}
              label="仅 Textin"
              hint="锁定 · 失败不降级"
            />

            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={onResetSegments} className="text-[12.5px]">
              恢复初始分段
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </>
  )

  if (inline) {
    // 嵌入顶栏：只输出按钮组，justify-end 让它们靠向右侧的 不接/归案。
    // 显隐按阅读器净宽（FixedReader @container）：并排 AI 助手让位后阅读器
    // 实际只有几百像素宽，视口断点会让工具组在顶栏里挤成一团
    return <div className="hidden @min-[1100px]:flex min-w-0 flex-1 items-center justify-end gap-2 text-[12.5px]">{tools}</div>
  }

  return (
    // 外层只负责边框底色与手机端右缘渐变（渐变得挂在不滚动的层上，否则跟着内容一起滚走）
    <div className="relative flex-none border-b border-border bg-card hidden @max-[1100px]:block max-[760px]:after:pointer-events-none max-[760px]:after:absolute max-[760px]:after:inset-y-0 max-[760px]:after:right-0 max-[760px]:after:w-8 max-[760px]:after:bg-gradient-to-l max-[760px]:after:from-card max-[760px]:after:to-transparent">
      <div className="mp-rd-toolbar text-[12.5px]">{tools}</div>
    </div>
  )
}

/**
 * 设置项：左侧勾选位固定宽度，右侧「标签 + 一句后果」。
 *
 * 为什么把后果写出来：这几个选项都**直接影响费用与结果可信度**
 * （补版面按页计费、锁定平台失败即失败），只写一个名词用户无从判断。
 * 勾选位用固定宽度而不是「标签后面跟 ✓」，是为了让两行文案左对齐。
 */
function PickItem({
  checked,
  onSelect,
  label,
  hint,
}: {
  checked: boolean
  onSelect: () => void
  label: string
  hint: string
}) {
  return (
    <DropdownMenuItem onSelect={onSelect} className="items-start gap-2 py-1.5">
      <span className="mt-[2px] flex h-3.5 w-3.5 flex-none items-center justify-center">
        {checked && <Check className="h-3.5 w-3.5" />}
      </span>
      <span className="min-w-0">
        <span className="block text-[12.5px] leading-4">{label}</span>
        <span className="block text-[11px] leading-4 text-muted-foreground">{hint}</span>
      </span>
    </DropdownMenuItem>
  )
}

/** 主按钮的悬浮说明：一眼看出这次会用什么策略跑 */
function autoSplitTitle(layoutMode: 'fast_text' | 'layout', cloudBackend: 'auto' | 'mineru' | 'textin'): string {
  const layout = layoutMode === 'layout' ? '补版面' : '仅文本层'
  const backend = cloudBackend === 'auto' ? '自动容灾' : cloudBackend === 'mineru' ? '仅 MinerU' : '仅 Textin'
  return `逐页识别并生成分段建议（${layout} · ${backend}）· 点右侧箭头可改设置`
}
