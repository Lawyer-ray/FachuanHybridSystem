/**
 * 「选中消息正文 → 浮条」的选区采集 hook。
 *
 * 只做一件事：把 `window.getSelection()` 里**落在消息正文容器内**的那段选区
 * 变成一个可渲染的快照（文字 + 矩形 + 所在容器）。定位、按钮、写入 store 都在
 * `components/SelectionBar.tsx`，那边才是 UI。
 *
 * 三个刻意的取舍：
 *
 * 1. **只在正文容器内生效**（`data-copilot-selection-root`）。浏览器里选区可以
 *    横跨整个文档：从回答拖到输入框、或从这条回答拖到下一条，都会产出一个
 *    「半截在别处」的选区。判据用 `range.commonAncestorContainer`——跨容器的
 *    选区共祖在容器之上，直接查不到 root，于是被整段拒掉，而不是把两个来源
 *    拼成一段假引用。
 * 2. **快照而非活引用**。`Selection`/`Range` 会被后续点击、输入、重渲染作废，
 *    组件里拿着它去读 rect 只会拿到 0。这里当场取成纯数据，之后 DOM 怎么变都
 *    不影响已算好的浮条位置。
 * 3. **取 `range.getBoundingClientRect()` 的并集，不用鼠标点**。多行选区的鼠标
 *    终点常落在行尾空白里，用它定锚会让浮条偏出半行；并集矩形同时给了浮条
 *    「该在选区上方还是下方」的判断依据（见 `placeSelectionBar`）。
 */

import { useCallback, useEffect, useState } from 'react'

import { normalizeSelectionText } from '../domain'

/** 消息正文容器的标记（`MessageList` 写在气泡正文那一层；跨模块靠属性约定，不 import 组件） */
export const SELECTION_ROOT_SELECTOR = '[data-copilot-selection-root]'

/** 视口坐标下的矩形快照（DOMRect 是活引用，不能存进 state） */
export interface RectSnapshot {
  top: number
  left: number
  right: number
  bottom: number
  width: number
  height: number
}

export interface SelectionAnchor {
  /** 选中原文（已 trim；供「复制」原样使用，不截断） */
  text: string
  /** 引用用文本（换行归一 + 限长，与引用卡/出站块的整形一致，见 domain/reference.ts） */
  quoteText: string
  /** 选区并集矩形（视口坐标） */
  rect: RectSnapshot
  /** 选区所在的正文容器（定位时从它向上找滚动容器） */
  root: HTMLElement
}

function rectOfRange(range: Range): RectSnapshot | null {
  // 两处探测不是洁癖：只有 CSSOM View 才规定 Range 有 getBoundingClientRect，
  // 老 WebView / jsdom 上它压根不存在（直接调用就是 TypeError，浮条永远不出现）。
  // 拿不到就退到 client rects 的首块，再拿不到就当作「无可用锚点」。
  const rect =
    typeof range.getBoundingClientRect === 'function' ? range.getBoundingClientRect() : range.getClientRects()[0]
  // 折叠/隐藏（display:none 里的选区）时全 0：没有可用锚点，不画浮条
  if (!rect || (rect.width === 0 && rect.height === 0)) return null
  return { top: rect.top, left: rect.left, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height }
}

/** 选区共祖所在的正文容器；跨容器选区（共祖在容器之上）返回 null */
function selectionRootOf(range: Range): HTMLElement | null {
  const node = range.commonAncestorContainer
  const el = node.nodeType === 1 /* ELEMENT_NODE，不用全局 Node 以免非浏览器环境报错 */ ? (node as HTMLElement) : node.parentElement
  return el?.closest<HTMLElement>(SELECTION_ROOT_SELECTOR) ?? null
}

/** 读取当前选区快照；不在正文容器内 / 为空 / 不可测 → null */
export function readSelectionAnchor(): SelectionAnchor | null {
  const selection = window.getSelection?.()
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null
  const text = selection.toString().replace(/\s+$/, '')
  if (!text.trim()) return null
  const range = selection.getRangeAt(0)
  const root = selectionRootOf(range)
  if (!root) return null
  const rect = rectOfRange(range)
  if (!rect) return null
  return { text, quoteText: normalizeSelectionText(text), rect, root }
}

/**
 * 采集消息正文选区的快照（null = 没有可用选区）。
 *
 * 监听四路是各有分工的，少一路就有明显缺口：
 * - `mouseup`：拖选真正结束的时刻（`selectionchange` 在拖动过程中一路狂发，
 *   只靠它会做出「跟着鼠标抖」的浮条）；
 * - `selectionchange`：折叠时立刻收浮条（点别处、清选区）；另外在拖到窗口外
 *   松手（收不到 mouseup）时用一帧 rAF 兜底补读；
 * - `keyup`：Shift+方向键、Ctrl+A 这类纯键盘选区（不产生 mouseup）；
 * - `scroll`（capture）/`resize`：矩形随滚动立刻失效，留着浮条只会悬在错的地方。
 */
export function useSelectionQuote(): { anchor: SelectionAnchor | null; clear: () => void } {
  const [anchor, setAnchor] = useState<SelectionAnchor | null>(null)
  const clear = useCallback(() => setAnchor(null), [])

  useEffect(() => {
    const read = () => setAnchor(readSelectionAnchor())
    // 折叠 = 用户放弃了选区，同步清（不排队，避免「已经点了别处浮条还在」）
    const onSelectionChange = () => {
      const selection = window.getSelection?.()
      if (!selection || selection.isCollapsed) {
        setAnchor(null)
        return
      }
      // 非折叠：拖选进行中/跨窗口松手，一帧后再读，避免每个字都渲染一次
      requestAnimationFrame(read)
    }
    const hide = () => setAnchor(null)

    document.addEventListener('selectionchange', onSelectionChange)
    document.addEventListener('mouseup', read)
    document.addEventListener('keyup', read)
    document.addEventListener('scroll', hide, true)
    window.addEventListener('resize', hide)
    return () => {
      document.removeEventListener('selectionchange', onSelectionChange)
      document.removeEventListener('mouseup', read)
      document.removeEventListener('keyup', read)
      document.removeEventListener('scroll', hide, true)
      window.removeEventListener('resize', hide)
    }
  }, [])

  return { anchor, clear }
}
