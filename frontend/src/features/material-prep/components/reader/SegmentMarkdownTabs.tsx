import { PencilLine, X } from 'lucide-react'

import type { MarkdownViewMode } from './SegmentMarkdownView'
import { ViewTab } from './ViewTab'

/** 正文面板的视图态：三档只读视图 + 「编辑整段」 */
export type SegmentMarkdownTab = MarkdownViewMode | 'blocks'

/**
 * 正文面板的视图切换器（唯一的切换入口）。
 *
 * 同一个状态有三个入口：这里的文字 tab、右侧 ✎（整段编辑）、页面框双击（进某一行
 * 修改态），三者都改父级的同一个 `view`——一个侧边栏里出现两套切换器，就会出现
 * 「控件从两个变三个、选中态还换一套样式」的那种混乱。
 *
 * **编辑态整行不渲染**（由调用方判 `tab !== 'edit'` 决定挂不挂）：点 tab 会直接卸载
 * textarea，等于静默丢掉没保存的正文；编辑态自己那条「保存整段 / 取消」才是出口。
 */
export function SegmentMarkdownTabs({
  tab,
  hasBlocks,
  onSelect,
  focusedBlockKey,
  onLocateBlock,
  onEditMarkdown,
}: {
  /** 当前视图（已归一：没有定位块时不会是 'blocks'） */
  tab: SegmentMarkdownTab
  /** 有定位块才有「分块」这一档 */
  hasBlocks: boolean
  onSelect: (view: MarkdownViewMode | 'blocks') => void
  focusedBlockKey: string | null
  /** 取消定位（传 null）；「定位中」时这里换成真出口 */
  onLocateBlock: (key: string | null) => void
  /** 有整段编辑能力时才显示 ✎ */
  onEditMarkdown?: (md: string) => void
}) {
  return (
    <div className="flex items-center gap-0.5 px-1">
      {hasBlocks && (
        <ViewTab active={tab === 'blocks'} onClick={() => onSelect('blocks')}>
          分块
        </ViewTab>
      )}
      <ViewTab active={tab === 'render'} onClick={() => onSelect('render')}>
        渲染
      </ViewTab>
      <ViewTab active={tab === 'source'} onClick={() => onSelect('source')}>
        源码
      </ViewTab>
      <span className="ml-auto" />
      {/* 一次性教学文案：只在分块视图、且有地方放的时候出现（容器窄于 320px 直接不显示，
          它不该跟 tab 抢同一行）。定位中换成「取消定位」，那是当下真正要给的出口。 */}
      {tab === 'blocks' &&
        (focusedBlockKey ? (
          <button
            type="button"
            onClick={() => onLocateBlock(null)}
            className="flex flex-none items-center gap-0.5 rounded px-1 pb-1 text-[10.5px] text-muted-foreground transition-colors hover:text-foreground"
          >
            <X className="h-3 w-3 flex-none" aria-hidden />
            取消定位
          </button>
        ) : (
          <span
            title={onEditMarkdown ? '双击某一行定位到原页；右键改这一行' : '双击某一行定位到原页'}
            className="hidden flex-none pb-1 text-[10.5px] text-muted-foreground/60 @[320px]:inline"
          >
            {onEditMarkdown ? '双击定位 · 右键改行' : '双击定位'}
          </span>
        ))}
      {onEditMarkdown && (
        <button
          type="button"
          aria-label="编辑整段"
          title="整段编辑 Markdown（保存后以整段正文为准）"
          onClick={() => onSelect('edit')}
          className="flex h-5 w-5 flex-none items-center justify-center rounded text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <PencilLine className="h-3 w-3" aria-hidden />
        </button>
      )}
    </div>
  )
}
