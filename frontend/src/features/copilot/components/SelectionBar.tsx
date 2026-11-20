/**
 * 选中即引用：在消息正文里选一段 → 浮条 `[复制] [引用到输入框]`。
 *
 * 「引用」直接写 `store.setPendingQuote`（已有动作，语义 = 新选区覆盖旧选区），
 * 输入框上方的 `ComposerQuote` 会自己渲染出来——这里不碰草稿，也不碰发送。
 *
 * ## 定位为什么不能直接用选区 rect
 *
 * 选区 rect 是**视口坐标**，而浮条要落在一个「既属于消息区、又不压输入框」的
 * 区域里（DSH `text-interaction.ts` 的 `visibleBounds` 就是干这个的）：
 *
 * 1. 扣掉**祖先滚动容器**的可见框：长回答里滚动容器只露出中间一屏，选区在
 *    视口内但视觉上早已被裁掉，浮条会浮在页脚/页头上面；
 * 2. 扣掉**输入框占位**（composer seat）的下沿：选中靠底部的文字时，选区下方
 *    紧挨着输入框，浮条若按「优先放下面」的默认规则就会压在输入框上，看起来
 *    像是输入区的一部分，点它也点不到；
 * 3. 最后按浮条自身尺寸**夹取**进这个可见框，宁可贴着边界也不越界。
 *
 * 三个步骤都在 `placeSelectionBar` / `visibleBoundsOf` 里，纯函数 + 单测。
 */

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { Check, Copy, Quote } from 'lucide-react'

import { useCopyFeedback } from '@/hooks/use-copy-feedback'

import type { SelectionAnchor, RectSnapshot } from '../hooks/use-selection-quote'
import { useSelectionQuote } from '../hooks/use-selection-quote'
import { useCopilot } from '../store'
import type { SelectionQuote } from '../types'

/** 滚动容器的标记（MessageList 写；跨模块靠属性约定，不 import 组件） */
const SCROLL_ROOT_SELECTOR = '[data-copilot-scroll]'
/** 输入区座位的标记；没人写时回落到 textarea 的祖先推断（见 composerSeatTop） */
const COMPOSER_SEAT_SELECTOR = '[data-copilot-composer-seat]'

/** 浮条与选区/边界之间的最小间距 */
const BAR_GAP = 8
/** 量不到真实尺寸时的保守估算（jsdom / 首帧未布局）。宁可估大：估小会压住输入框 */
const BAR_FALLBACK_SIZE = { width: 132, height: 30 }
/** 引用卡显示来源用的固定文案（见下方 quoteFromSelection 的注释） */
const CHAT_QUOTE_SUBPATH = '对话选段'

interface VisibleBounds {
  top: number
  left: number
  right: number
  bottom: number
}

interface BarSize {
  width: number
  height: number
}

interface BarPlacement {
  top: number
  left: number
  placement: 'below' | 'above'
}

function clamp(value: number, min: number, max: number): number {
  // max < min 时（可见框比浮条还窄/矮）以 min 为准，保证浮条仍然贴在可见框内侧
  return Math.min(Math.max(value, min), Math.max(min, max))
}

/**
 * 浮条该放哪（纯函数）。
 *
 * 优先放在选区下方（豆包/Notion 的惯例：不遮挡刚读的那一行）；下方放不下
 * （临近输入框/滚动容器下沿）再翻到上方；两边都不够就夹进去。
 */
function placeSelectionBar(
  anchor: Pick<RectSnapshot, 'top' | 'left' | 'width' | 'bottom'>,
  bounds: VisibleBounds,
  size: BarSize,
  gap: number = BAR_GAP,
): BarPlacement {
  const below = anchor.bottom + gap
  const above = anchor.top - size.height - gap
  const maxBottom = bounds.bottom - size.height - gap
  const minTop = bounds.top + gap

  let placement: 'below' | 'above' = 'below'
  let top = below
  if (below > maxBottom) {
    placement = 'above'
    top = above
  }
  top = clamp(top, minTop, maxBottom)

  const left = clamp(anchor.left + anchor.width / 2 - size.width / 2, bounds.left + gap, bounds.right - size.width - gap)
  return { top, left, placement }
}

/** 选区所在的最近可滚动祖先（属性约定优先，其次按计算样式找） */
function scrollerOf(root: HTMLElement | null): HTMLElement | null {
  if (!root) return null
  const tagged = root.closest<HTMLElement>(SCROLL_ROOT_SELECTOR)
  if (tagged) return tagged
  // 兜底：面板外壳可能换成别的滚动容器，按 overflow 找比写死选择器稳
  for (let el = root.parentElement; el; el = el.parentElement) {
    const { overflowY } = window.getComputedStyle(el)
    if (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') return el
  }
  return null
}

/**
 * 输入区占位的上沿（浮条的下边界）。
 *
 * 为什么不用固定像素：输入框高度随附件 chips / 引用条 / 多行草稿变化，写死一个
 * 数字迟早会错位。这里先找 `[data-copilot-composer-seat]` 标记；没有标记就取
 * 页面里的 textarea，向上扩到「底部贴着视口下沿」的最外层容器（那就是整个输入区，
 * 包含它上方的引用条与工具条）。
 */
function composerTextarea(): HTMLElement | null {
  const seat = document.querySelector<HTMLElement>(COMPOSER_SEAT_SELECTOR)
  if (seat) return seat
  // 不能直接 `document.querySelector('textarea')`：转录里的结构化提问卡也有 textarea，
  // 它在 DOM 里排在输入区之前，拿它当座位会把浮条挤到上沿。输入区在消息区之后，
  // 所以取「不属于消息滚动容器」的最后一个。
  const areas = Array.from(document.querySelectorAll<HTMLElement>('textarea'))
  return areas.filter((el) => !el.closest(SCROLL_ROOT_SELECTOR)).at(-1) ?? areas.at(-1) ?? null
}

function composerSeatTop(): number | null {
  const textarea = composerTextarea()
  if (!textarea) return null
  const rect = textarea.getBoundingClientRect()
  if (!rect.height) return null // 未布局（jsdom）：交给视口下沿兜底
  let top = rect.top
  for (let el = textarea.parentElement; el && el !== document.body; el = el.parentElement) {
    const outer = el.getBoundingClientRect()
    if (outer.bottom < window.innerHeight - 1) break
    if (outer.top > 0) top = Math.min(top, outer.top)
  }
  return top
}

/** 浮条可用的可见框：视口 ∩ 滚动容器可见框，再被输入区占位抬高下沿 */
function visibleBoundsOf(root: HTMLElement | null): VisibleBounds {
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0
  const scroller = scrollerOf(root)
  const scrollerRect = scroller?.getBoundingClientRect()
  const top = Math.max(0, scrollerRect?.top ?? 0)
  const left = Math.max(0, scrollerRect?.left ?? 0)
  const right = Math.min(viewportWidth, scrollerRect?.right ?? viewportWidth)
  const seat = composerSeatTop()
  const bottom = Math.min(viewportHeight, scrollerRect?.bottom ?? viewportHeight, seat ?? Number.POSITIVE_INFINITY)
  return { top, left, right, bottom }
}

/**
 * 选区 → 待发引用（`SelectionQuote`）。
 *
 * **没有会话归属时返回 null，不编造 id**。`SelectionQuote` 的形状是「哪个文件
 * 的哪一段」（`kind` + `ownerId` + `subpath`），出站会被拼成
 * `[已引用选段："…" (case_id=N, subpath="…")]`。消息正文的选段本身没有归属，
 * 唯一诚实的 id 来源是会话的业务范围（`store.context`，从案件/合同页打开助手时
 * 才有）。填 0 或拿消息主键去顶 `case_id` 会让模型拿着一个不存在的案件去查——
 * 那比「按钮说明为什么不可用」坏得多（同样的取舍见 domain/message-id.ts）。
 */
function quoteFromSelection(anchor: SelectionAnchor, context: { origin: 'case' | 'contract'; refId: number } | null): SelectionQuote | null {
  if (!context || !(context.refId > 0)) return null
  return {
    kind: context.origin,
    ownerId: context.refId,
    subpath: CHAT_QUOTE_SUBPATH,
    name: CHAT_QUOTE_SUBPATH,
    text: anchor.quoteText,
  }
}

/**
 * 挂载点：自己持有选区状态再渲染浮条。
 *
 * 为什么让这个叶子组件持有而不是 MessageList：`selectionchange` 在拖选过程中
 * 高频触发，状态放在列表组件里等于每一帧都让整条转录重渲染一次。
 */
export function SelectionBarLayer() {
  const { anchor, clear } = useSelectionQuote()
  const setPendingQuote = useCopilot((s) => s.setPendingQuote)
  const context = useCopilot((s) => s.context)
  const reasonId = `copilot-quote-reason-${useId()}`
  const barRef = useRef<HTMLDivElement>(null)
  const [placement, setPlacement] = useState<BarPlacement | null>(null)
  const { copied, copy } = useCopyFeedback({ resetMs: 1500 })

  const quote = anchor ? quoteFromSelection(anchor, context) : null

  // 先渲染、再按真实尺寸夹取定位（首帧 hidden，不会闪到错位置）
  useLayoutEffect(() => {
    if (!anchor) {
      setPlacement(null)
      return
    }
    const rect = barRef.current?.getBoundingClientRect()
    const size = {
      width: rect?.width || BAR_FALLBACK_SIZE.width,
      height: rect?.height || BAR_FALLBACK_SIZE.height,
    }
    setPlacement(placeSelectionBar(anchor.rect, visibleBoundsOf(anchor.root), size))
  }, [anchor])

  const dismiss = useCallback(() => {
    clear()
    // 连 DOM 选区一起清：否则下一次 selectionchange（点别处再点回来）会把浮条复活
    window.getSelection()?.removeAllRanges()
  }, [clear])

  // Esc 关掉浮条。**不抢焦点**：浮条出现时不 .focus()，律师的选区与后续 Tab
  // 顺序都不受影响；但按钮仍在 DOM 里，键盘用户 Tab 得进去。
  useEffect(() => {
    if (!anchor) return
    const onKeyDown = (event: KeyboardEvent) => {
      // 输入法组合期的 Esc 是「取消候选」，不能顺带把浮条也收掉
      if (event.key !== 'Escape' || event.isComposing) return
      dismiss()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [anchor, dismiss])

  if (!anchor) return null

  return (
    <div
      ref={barRef}
      role="toolbar"
      aria-label="所选文字的快捷操作"
      // 不抢焦点、也不让 mousedown 的默认行为清掉选区——一清选区，
      // selectionchange 立刻把浮条收走，click 就永远落不到按钮上
      onMouseDown={(event) => event.preventDefault()}
      style={{
        position: 'fixed',
        top: placement?.top ?? -9999,
        left: placement?.left ?? -9999,
        visibility: placement ? 'visible' : 'hidden',
      }}
      className="z-50 flex items-center gap-0.5 rounded-[9px] border border-border bg-card px-1 py-1 shadow-md"
      data-placement={placement?.placement}
      data-testid="selection-bar"
    >
      <button
        type="button"
        className="flex h-6 items-center gap-1 rounded-[6px] px-1.5 text-[11.5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        onClick={() => void copy(anchor.text)}
        title="复制所选文字（原样，不截断）"
      >
        {copied ? <Check className="h-3 w-3 text-emerald-600" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
        {copied ? '已复制' : '复制'}
      </button>
      <button
        type="button"
        // 不可用时**可见但不可用**（原生 disabled 收不到 hover/focus，
        // 原因就永远弹不出来——同 DSH MessageIconActions 的写法）
        aria-disabled={quote ? undefined : true}
        aria-describedby={quote ? undefined : reasonId}
        title={quote ? '引用到输入框' : '当前是通用对话，选段没有可归属的案件/合同'}
        className={
          'flex h-6 items-center gap-1 rounded-[6px] px-1.5 text-[11.5px] transition-colors ' +
          (quote ? 'text-foreground hover:bg-secondary' : 'cursor-not-allowed text-muted-foreground opacity-50')
        }
        onClick={() => {
          if (!quote) return
          // 新选区直接覆盖旧选区（store.setPendingQuote 的既有语义）
          setPendingQuote(quote)
          dismiss()
        }}
      >
        <Quote className="h-3 w-3" aria-hidden />
        引用到输入框
      </button>
      <span id={reasonId} className="sr-only">
        这条回答所在的是通用对话，没有关联的案件或合同，选段无法带上业务归属；在案件或合同页面打开助手后再引用。
      </span>
    </div>
  )
}
