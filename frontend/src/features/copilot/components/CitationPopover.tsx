/**
 * 角标点开后的「来源卡片」：来源名 + 定位 + 原文片段 +（能跳时）打开原文。
 *
 * **为什么不是 Radix Popover**：仓库装的是 alert-dialog / context-menu / dialog /
 * dropdown-menu / slot，**没有** `@radix-ui/react-popover`；本次改动不允许新增
 * 依赖，所以这里用 `createPortal` + fixed 定位自己实现，键盘行为（Esc 关闭、
 * 焦点归还角标）由 `CitationMark` 显式接管。功能面只有这一处需要，不值得为它
 * 引一个包。
 *
 * **为什么用 portal + fixed 而不是 absolute**：角标会出现在 Markdown 表格的单元
 * 里，而表格外层为了长表格必须 `overflow-auto`——absolute 的卡片会被那条滚动
 * 容器整块裁掉（律师点开只看到半行）。portal 到 body + 视口坐标不受祖先裁剪，
 * 再按视口上下翻转，贴在栏底/栏顶的角标也不会把卡片顶出屏幕。
 *
 * **措辞是合规问题，不是体验问题**：解析器给的页号对 PDF 是物理页、对 docx/txt
 * 是**分段批次**。这里统一走 `pageSpanNote`，「第 3 页」与「第 3 段（按解析分段）」
 * 由它决定；本文件不许自己拼页号文案——律师按「第 3 页」去翻纸质卷翻不到，
 * 是把责任推给了用户。
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router'

import { bankLitigation, projectDetail } from '@/app/paths'

import { pageSpanNote, type CitationKind, type CitationRef } from '../domain/knowledge'

/** 卡片宽度：够放两行来源名 + 三行原文，又不至于在小栏里横着溢出 */
const PANEL_WIDTH = 320
/** 与视口边缘的最小间距（贴边时也不会被圆角/滚动条切掉） */
const VIEWPORT_MARGIN = 8
/** 与角标之间的间距 */
const ANCHOR_GAP = 6

/** 来源种类的短标签（窄卡片里放不下长名词） */
const KIND_LABEL: Record<CitationKind, string> = {
  case: '案件',
  contract: '合同',
  statute: '法条',
  judgment: '裁判文书',
  file: '材料',
}

/**
 * 定位文案。
 *
 * 条款号优先：法条/合同里「第 7.2 条」比「第 12 页」精确得多；没有条款号才退回
 * 页（并且必须经 `pageSpanNote` 转换措辞）。两者都没有就如实说「未标注定位」，
 * 不编一个页码。
 */
function locationNote(citation: CitationRef): string {
  if (citation.clause !== undefined && citation.clause.length > 0) return `第 ${citation.clause} 条`
  if (citation.page !== undefined) return pageSpanNote(citation.page, citation.kind)
  return '未标注定位'
}

/** 正则元字符转义：关键词来自检索词，可能带括号/点号 */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 把原文片段按命中关键词切成「文字 / 高亮」片段。
 *
 * 关键词缺失（后端还没发检索词）时返回 **原字符串**，整段不高亮——宁可不
 * 高亮，也不按空格/标点瞎猜，把半句原文涂成荧光色。
 */
function highlightParts(text: string, keywords: readonly string[] | undefined): React.ReactNode {
  const words = (keywords ?? []).map((w) => w.trim()).filter((w) => w.length > 0)
  if (words.length === 0) return text

  // 长词优先：短词是长词的子串时（「合同」/「合同解除」）先匹配长的，避免把长词切碎
  const pattern = new RegExp(`(${words.sort((a, b) => b.length - a.length).map(escapeRegExp).join('|')})`, 'gi')
  const parts = text.split(pattern)
  return parts.map((part, index) =>
    // split 带捕获组时奇数位就是命中项，正好用下标判断，不必再比一遍正则
    index % 2 === 1 ? (
      <mark key={index} className="rounded-[2px] bg-amber-200 px-0.5 text-inherit dark:bg-amber-500/30">
        {part}
      </mark>
    ) : (
      part
    ),
  )
}

/**
 * 「打开原文」的目标。
 *
 * 只有能跳到实体页的来源才给按钮：`statute` / `judgment` / `file` 目前没有
 * 独立的详情路由，给一个点了 404 的按钮比不给更糟。
 */
function openTarget(citation: CitationRef): { to: string; label: string } | null {
  if (citation.refId === undefined) return null
  if (citation.kind === 'case') return { to: bankLitigation(citation.refId), label: '在案件中打开' }
  if (citation.kind === 'contract') return { to: projectDetail(citation.refId), label: '在合同中打开' }
  return null
}

/** 卡片相对角标的落点（视口坐标）：默认贴下方，放不下就翻到上方 */
function placePanel(
  anchor: { left: number; top: number; bottom: number },
  panel: { width: number; height: number },
): React.CSSProperties {
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight
  const preferredLeft = anchor.left

  const maxLeft = Math.max(VIEWPORT_MARGIN, viewportWidth - PANEL_WIDTH - VIEWPORT_MARGIN)
  const left = Math.min(Math.max(preferredLeft, VIEWPORT_MARGIN), maxLeft)

  const below = anchor.bottom + ANCHOR_GAP
  const above = anchor.top - panel.height - ANCHOR_GAP
  const top = below + panel.height > viewportHeight - VIEWPORT_MARGIN ? Math.max(VIEWPORT_MARGIN, above) : below

  return { left, top, width: PANEL_WIDTH }
}

export function CitationPopover({
  citation,
  open,
  anchorRef,
  onClose,
}: {
  citation: CitationRef
  open: boolean
  /** 触发角标，用于定位与「点卡片外面关闭」的判定 */
  anchorRef: React.RefObject<HTMLElement | null>
  /** 关闭；`restoreFocus` 只在键盘关闭时为 true（鼠标点外面时焦点已跟着鼠标走） */
  onClose: (restoreFocus: boolean) => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState<React.CSSProperties>({ visibility: 'hidden' })

  const place = useCallback(() => {
    const anchor = anchorRef.current
    const panel = panelRef.current
    if (!anchor || !panel) return
    setPosition(placePanel(anchor.getBoundingClientRect(), panel.getBoundingClientRect()))
  }, [anchorRef])

  useLayoutEffect(() => {
    if (!open) return
    place()
    // 面板刚挂载时还没尺寸（layout 后才有），再量一次
    const raf = window.requestAnimationFrame(place)
    // 捕获阶段监听：消息区自己是个滚动容器，scroll 不冒泡到 window
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      window.cancelAnimationFrame(raf)
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open, place])

  // 打开后把焦点送进卡片：卡片里可能有「打开原文」链接，
  // 不送焦点的话键盘用户 Tab 一路走过正文也进不到这里
  useEffect(() => {
    if (!open) return
    panelRef.current?.focus()
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      // 只吃掉这一层：面板常开在对话框/抽屉里，不 stopPropagation 会连带关掉外层
      event.stopPropagation()
      onClose(true)
    }
    const onPointerDown = (event: Event) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (panelRef.current?.contains(target) || anchorRef.current?.contains(target)) return
      onClose(false)
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('pointerdown', onPointerDown, true)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('pointerdown', onPointerDown, true)
    }
  }, [open, onClose, anchorRef])

  if (!open) return null

  const target = openTarget(citation)

  return createPortal(
    <div
      ref={panelRef}
      role="dialog"
      aria-label={`来源 ${citation.citeNo}：${citation.name}`}
      tabIndex={-1}
      style={position}
      className="fixed z-[120] rounded-lg border border-border bg-popover p-3 text-left text-popover-foreground shadow-xl outline-none"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-[12.5px] font-medium">{citation.name}</span>
        <span className="shrink-0 rounded-[4px] bg-secondary px-1 py-0.5 text-[10px] text-muted-foreground">
          {KIND_LABEL[citation.kind]}
        </span>
      </div>

      <div className="mt-1 text-[11px] text-muted-foreground">{locationNote(citation)}</div>

      {citation.text !== undefined && citation.text.length > 0 ? (
        <p className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap break-words text-[12px] leading-relaxed">
          {highlightParts(citation.text, citation.keywords)}
        </p>
      ) : (
        // 引用表里没带原文时如实说明：律师需要知道「看不到原文」不是因为自己没找到
        <p className="mt-2 text-[11.5px] text-muted-foreground">原文未随本轮保存</p>
      )}

      {target !== null && (
        <Link
          to={target.to}
          className="mt-2 inline-block text-[11.5px] text-foreground underline underline-offset-2"
          onClick={() => onClose(false)}
        >
          {target.label}
        </Link>
      )}
    </div>,
    document.body,
  )
}
