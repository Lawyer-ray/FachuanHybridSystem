/**
 * 会话滚动位置记忆：**语义锚点**（`anchorKey` + `anchorTop`），`scrollTop` 只兜底。
 *
 * 真实场景（为什么要这个 hook）：律师在 A 案件会话里往上翻到三个月前第 4 轮的
 * 某段分析，切去 B 会话回一封邮件，再切回 A——位置丢了，得重新往上翻几十屏。
 * `MessageList` 现在只有 `atBottom` 布尔 + 贴底，切回来永远落到底部。
 *
 * 为什么不是「记住 scrollTop」：
 * - 转录高度是会变的（流式增量、图片加载、工具行展开、翻页时上面插入一整页）。
 *   同一个 `scrollTop` 在不同高度下指向完全不同的内容——翻一页 200 条插在顶上，
 *   旧 `scrollTop` 就指到别处去了。
 * - 「读到哪里」的真正身份是**哪一行 + 该行顶部在视口里的偏移**（第一段已读文本
 *   距视口顶 -40px），行的位置变了锚点跟着走，这才是用户认的位置。
 * - 行都没了（消息被删/被合并/换了一批）时才退回 `scrollTop`，那是最后的兜底。
 *
 * 为什么存内存 Map 而不是 localStorage / 后端：
 * - `anchorTop`、`scrollTop` 都是**与窗口尺寸相关**的量。存进 localStorage 就会被
 *   跨设备、跨窗口宽度同步：在 1440px 宽的抽屉里读到第 4 轮，
 *   在笔记本 1280px 或折叠成手机宽度打开，同一份数字落到完全不同的位置——
 *   跳到莫名其妙的地方，比不恢复更糟。
 * - 存后端要新增「会话视图状态」表/字段，而这份状态的寿命就是一个页面会话
 *   （内存 Map 随刷新重置，正好符合「刷新后回到最新消息」的预期）。
 * 结论：宿主侧 per-session 内存 Map，`Map<sessionId, ChatScrollPosition>`。
 *
 * 与浏览器原生锚定（`overflow-anchor`）的关系：**全程关掉**。自定义锚点在
 * session 切换/翻页时才校正一次，而原生锚定在每一次布局变化时都会自己撑住
 * `scrollTop`；两套同时开着就会互相打架（典型表现：翻页后位置抖两下、
 * 或者被原生锚定撑在了错误的行上）。所以只要用了本 hook，滚动容器恒为
 * `overflow-anchor: none`。
 *
 * 用法见文件末尾的「接线」注释；本文件只提供 hook 与测试，不接进 `MessageList`。
 */

import { useCallback, useEffect, useRef } from 'react'
import type { RefObject } from 'react'

/** 行身份标记：视口内第一个带它的元素即锚点（由 `MessageList` 给每条消息加） */
const ROW_ATTR = 'data-msg-id'

/**
 * 一条会话的阅读位置（形状照 DSH `ChatScrollPosition`，
 * `_refs/deepseek-harness/packages/client/ui-chat/src/client/contract/slots.ts:309-313`）。
 */
export interface ChatScrollPosition {
  /** 锚点行的语义 id（`data-msg-id` 的值）；空串 = 保存时视口里一行都没有 */
  readonly anchorKey: string
  /** 该行顶部相对滚动容器顶部的偏移（负数 = 行的上半截被切在视口外） */
  readonly anchorTop: number
  /** 兜底：锚点行已不在时用它（仅在会话内高度不变时才有意义） */
  readonly scrollTop: number
}

/**
 * per-session 位置表（模块级 = 宿主侧，跟着页面活）。
 *
 * 刻意**不**做上限淘汰：一条记录只有 3 个数字，哪怕 100 个会话也就几百字节，
 * 而淘汰策略会引入「刚翻过的会话反而被淘汰」这种难复现的问题。
 */
const anchors = new Map<string, ChatScrollPosition>()

/**
 * 清空位置表。测试用它做隔离；将来「删除会话」也可顺手调用（不清也只是留一条死记录）。
 */
export function clearScrollAnchors(): void {
  anchors.clear()
}

/** 只读入口，给测试与排障用（不暴露可变引用） */
export function readScrollAnchor(sessionId: string): ChatScrollPosition | undefined {
  return anchors.get(sessionId)
}

/**
 * 关掉浏览器原生滚动锚定（见文件头「为什么全程关掉」）。
 * 幂等：已经设置过就不再碰样式，避免每个 delta 都触发一次 style 写入。
 */
function disableNativeAnchor(el: HTMLElement): void {
  if (el.style.overflowAnchor !== 'none') el.style.overflowAnchor = 'none'
}

/** 属性值选择器的转义：`CSS.escape` 缺失（jsdom/旧环境）时退化为手动转义引号反斜杠 */
function escapeAttr(value: string): string {
  // 走 globalThis 而不是直接写 `CSS`：lib.dom 没有声明这个全局（jsdom 里才有），
  // 直接引用会让 tsc 报 not defined
  const css = (globalThis as unknown as { CSS?: { escape?: (v: string) => string } }).CSS
  if (typeof css?.escape === 'function') return css.escape(value)
  return value.replace(/["\\]/g, '\\$&')
}

/** 按语义 id 找行 */
function findRow(el: HTMLElement, key: string): HTMLElement | null {
  return el.querySelector<HTMLElement>(`[${ROW_ATTR}="${escapeAttr(key)}"]`)
}

/**
 * 视口内**第一条**行：`bottom > 容器顶` 即有至少 1px 露出来。
 *
 * 上半截被切在视口外的行也算（`top` 为负）——用户认的「我停在这一行」就是
 * 那半行，跳过它去取完整可见的下一条会让每次「保存→恢复」都往下漂一行。
 */
function firstVisibleRow(el: HTMLElement): { key: string; top: number } | null {
  const boxTop = el.getBoundingClientRect().top
  const rows = el.querySelectorAll<HTMLElement>(`[${ROW_ATTR}]`)
  for (const row of rows) {
    const rect = row.getBoundingClientRect()
    if (rect.bottom > boxTop) {
      const key = row.getAttribute(ROW_ATTR)
      if (key) return { key, top: rect.top - boxTop }
    }
  }
  return null
}

/**
 * 把 anchorKey 那一行重新对齐到 anchorTop 处，返回**实际移动的像素**。
 *
 * 返回 `null` = 行已不在（消息被删/换批），调用方据此回退 `scrollTop` 或停止校正。
 * 返回 `0` = 本来就对（恢复后立刻触发的那次 `ResizeObserver` 初始回调就是这种）。
 */
function alignTo(el: HTMLElement, anchorKey: string, anchorTop: number): number | null {
  const row = findRow(el, anchorKey)
  if (!row) return null
  const delta = row.getBoundingClientRect().top - el.getBoundingClientRect().top - anchorTop
  if (delta !== 0) el.scrollTop += delta
  return delta
}

/**
 * 滚动位置记忆。`scroller` 是滚动容器（`overflow-y-auto` 那一层）的 ref。
 *
 * 返回的两个动作都是幂等的「读/写一次」，不订阅 scroll 事件：位置只在
 * 「切走」和「切回」两个时刻需要，全程监听每个 scroll 事件反而会在流式
 * 期间与贴底逻辑抢 `scrollTop`。
 */
export function useScrollAnchor(scroller: RefObject<HTMLElement | null>): {
  saveAnchor: (sessionId: string | null) => void
  restoreAnchor: (sessionId: string | null) => void
} {
  const observerRef = useRef<ResizeObserver | null>(null)

  // 全程关掉原生锚定。放在每次渲染后而不是挂载时一次性设置：
  // 容器可能是条件渲染出来的（欢迎页/空态切换），也可能被别的组件重置样式。
  useEffect(() => {
    const el = scroller.current
    if (el) disableNativeAnchor(el)
  })

  // 卸载断开校正观察器：切页面时元素已销毁，回调里再动 scrollTop 只会报错
  useEffect(
    () => () => {
      observerRef.current?.disconnect()
      observerRef.current = null
    },
    [],
  )

  const saveAnchor = useCallback(
    (sessionId: string | null) => {
      const el = scroller.current
      if (!sessionId || !el) return
      disableNativeAnchor(el)
      const row = firstVisibleRow(el)
      anchors.set(sessionId, {
        anchorKey: row?.key ?? '',
        anchorTop: row ? row.top : 0,
        scrollTop: el.scrollTop,
      })
    },
    [scroller],
  )

  const restoreAnchor = useCallback(
    (sessionId: string | null) => {
      const el = scroller.current
      if (!sessionId || !el) return
      disableNativeAnchor(el)
      const pos = anchors.get(sessionId)
      // 无记录 = 这个会话第一次进来：**什么都不做**，让调用方的贴底逻辑决定位置。
      // （静默返回而不是滚到底/滚到顶——这里没有立场替调用方做决定。）
      if (!pos) return
      // 有锚点行走语义恢复；锚点为空（保存时是空态）或行已不在（消息被删/换批）
      // 才退回 scrollTop —— 那时没有语义可用，这是最后的兜底。
      const moved = pos.anchorKey ? alignTo(el, pos.anchorKey, pos.anchorTop) : null
      if (moved === null) {
        el.scrollTop = pos.scrollTop
        return
      }
      // 图片/字体的二次布局会把行推走：恢复后校正一次。没有 ResizeObserver
      // （jsdom / 很老的浏览器）就不校正——少一次美化，不是功能缺失。
      if (typeof ResizeObserver === 'undefined') return
      observerRef.current?.disconnect()
      const { anchorKey, anchorTop } = pos
      // 观察**内容容器**：滚动容器的 border-box 不会因为图片加载而变，内容高度才会。
      // 没有子元素时退化为观察滚动容器本身（至少能兜住窗口缩放）。
      const target = el.firstElementChild instanceof HTMLElement ? el.firstElementChild : el
      let idle = 0
      const stop = () => {
        ro.disconnect()
        if (observerRef.current === ro) observerRef.current = null
      }
      const ro = new ResizeObserver(() => {
        const delta = alignTo(el, anchorKey, anchorTop)
        // 行没了：无从校正，收工
        if (delta === null) return stop()
        // observe() 的初始回调必然来一次、且此时尺寸未变（delta === 0）。
        // 要留着观察器等下一次回调（图片/字体把行推偏了那次），但也不无限等：
        // 连续两次都没有偏移就说明没有二次布局，收工。
        if (delta === 0 && ++idle < 2) return
        stop()
      })
      observerRef.current = ro
      ro.observe(target)
    },
    [scroller],
  )

  return { saveAnchor, restoreAnchor }
}

/*
 * 接线（`MessageList.tsx`，归另一个 agent；本文件不碰）——三行：
 *
 *   // 1) 拿动作（scrollRef 就是已有的那个滚动容器 ref）
 *   const { saveAnchor, restoreAnchor } = useScrollAnchor(scrollRef)
 *   // 2) 现有的 handleScroll 里加一行：滚动即记（这是**唯一**量得准旧 DOM 的时机）
 *   saveAnchor(sessionId)
 *   // 3) 历史就位后恢复一次（loadingHistory 变 false 说明转录已渲染）
 *   useEffect(() => { if (!loadingHistory) restoreAnchor(sessionId) }, [sessionId, loadingHistory, restoreAnchor])
 *
 * 前提：每条消息的根节点要带 `data-msg-id={message.id}`（锚点身份，现有 `id`
 * 属性不够——它可能是 React 生成的），且滚动容器保持本 hook 设好的
 * `overflow-anchor: none`（别在 CSS 里改回来，否则两套锚定打架）。
 *
 * 第 2 行**不要**改成 `useEffect(() => () => saveAnchor(sessionId), [sessionId])`：
 * `useEffect` 的 cleanup 跑在「DOM 已经换成新会话（messages 已被清空）」之后，
 * 量到的是空转录，锚点白白丢失（只剩 `scrollTop` 兜底）。要用 effect 版本
 * 就必须写 `useLayoutEffect`——它的 cleanup 在 DOM 变更**之前**执行，量到的
 * 还是上一个会话的旧 DOM。放在已有的 scroll 回调里最省事也最稳。
 */
