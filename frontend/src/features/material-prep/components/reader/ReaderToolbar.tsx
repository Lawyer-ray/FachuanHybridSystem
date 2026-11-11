import { Check, ChevronDown, Loader2, Minus, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { PBTN, PBTN_ON, ZOOM_MAX, ZOOM_MIN } from './ui'
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
  maxCols,
  onSetCols,
  colsDisabled,
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
  /** 当前窗口宽度下最多能并排几列（<2 表示不够宽，不能并排） */
  maxCols: number
  /** 直接指定列数：菜单里点哪列就是哪列 */
  onSetCols: (n: number) => void
  colsDisabled: boolean
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

      <span className="h-4 w-px flex-none bg-border max-[760px]:hidden" />

      {/* 视图控件（缩放 + 并排列数）：原先这里是 5 个描边控件平铺
          （−/100%/+ 三个框 + 列数一个框 + 分隔线），常驻占掉 ~150px。
          问题是它们把**一整套缩放**拆成了三个同等权重的按钮，而百分比
          那个框看着像只读状态、点下去却是"重置"——没人会去点。
          现在收成一个入口：常驻只显示当前倍率，点开才有 −/+/重置/列数。
          缩放的主路径本来就是 ⌘/Ctrl+滚轮，按钮是备选，低频。 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={`视图设置：当前 ${zoomVal}%，${cols} 列`}
            title="视图：缩放与并排列数"
            className={cn(PBTN, 'min-w-[54px] justify-center gap-1 px-[7px] tabular-nums max-[760px]:hidden')}
          >
            {zoomVal}%
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[210px]">
          <DropdownMenuLabel className="text-[11px] font-normal text-muted-foreground">
            缩放
          </DropdownMenuLabel>
          {/* − / + 一行两列：缩放本质上是一个控件，排成一行比上下两行更好按，
              也避免用户为了"调小一点"要跨过整个菜单 */}
          <div className="flex items-center gap-1 px-1 pb-1">
            <button
              type="button"
              onClick={onZoomOut}
              disabled={zoomVal <= Math.round(ZOOM_MIN * 100)}
              aria-label="缩小画布"
              title="缩小（⌘/Ctrl + 滚轮）"
              className="flex h-7 flex-1 items-center justify-center rounded-[5px] border border-input text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Minus className="h-3.5 w-3.5" />
            </button>
            <span className="min-w-[46px] flex-none text-center text-[12.5px] tabular-nums">{zoomVal}%</span>
            <button
              type="button"
              onClick={onZoomIn}
              disabled={zoomVal >= Math.round(ZOOM_MAX * 100)}
              aria-label="放大画布"
              title="放大（⌘/Ctrl + 滚轮）"
              className="flex h-7 flex-1 items-center justify-center rounded-[5px] border border-input text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>
          {/* 重置做成明确的菜单项：原先它藏在"100%"那个框的点击里，没人发现 */}
          <DropdownMenuItem onSelect={onZoomReset} disabled={zoomVal === 100} className="text-[12.5px]">
            恢复到 100%
          </DropdownMenuItem>

          <DropdownMenuSeparator />
          <DropdownMenuLabel className="text-[11px] font-normal text-muted-foreground">
            并排页数
          </DropdownMenuLabel>
          {/* 按实际能排的列数逐项列出，而不是做成「单页/并排」二选一：
              原按钮是 1→2→3→…→1 的循环，二选一会在三列时显示成错的状态。 */}
          {Array.from({ length: Math.max(1, maxCols) }, (_, i) => i + 1).map((n) => (
            <PickItem
              key={n}
              checked={cols === n}
              onSelect={() => onSetCols(n)}
              label={n === 1 ? '单页' : `${n} 列`}
              hint={n === 1 ? '一列，适合精读' : `并排 ${n} 页`}
            />
          ))}
          {colsDisabled && (
            <p className="px-2 pb-1 pt-0.5 text-[11px] leading-4 text-muted-foreground">
              窗口还不够宽，并排至少每列 360px
            </p>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

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
