import type { EngineBlockRect } from '../../types'

/**
 * 把视口滚到「某页上某个块框」的位置。
 *
 * ## 为什么不能只 scrollIntoView(页)
 *
 * 一个扫描页在屏幕上有上千像素高。只滚到页顶的话，律师看到的仍然是整页图，
 * 还得自己往下找那一行——而他刚点的是一条「第 9 页这处两个引擎读得不一样」。
 * 滚到框的位置才是「带我去出问题的地方」。
 *
 * ## 坐标口径
 *
 * `rect.y` 是**相对页面图像**归一化的 0–1（与 `PositionedBlock.rect` 同一套）。
 * 乘上页面元素的 `getBoundingClientRect().height` 得到像素偏移。
 *
 * ## 为什么留 1/3 视口的余量
 *
 * 把目标框顶到屏幕最上沿会失去上下文（看不到前后文，判断不了这是什么表、
 * 哪一栏）。留 1/3 视口让它落在偏上位置，前后文都在。
 *
 * ## 没有坐标时什么都不做
 *
 * 约 11% 的分歧没有块坐标（后端没匹配到 block）。这时**不伪造精度**——
 * 调用方已先做了「只跳页」，这里直接返回即可。
 */
const PAGE_TOP_DELAY_MS = 260
const VIEWPORT_HEADROOM_RATIO = 1 / 3

export function scrollToEngineRects(mi: number, page: number, rects: EngineBlockRect[]): void {
  const usable = rects.map((r) => r.rect).filter((r): r is NonNullable<typeof r> => !!r)
  if (usable.length === 0) return

  const topY = Math.min(...usable.map((r) => r.y))

  // 延后一拍：调用方通常先 scrollIntoView(页)，两次滚动立刻连发会互相打断，
  // 最终停在页顶而不是框上。等第一次落位后再按坐标微调。
  window.setTimeout(() => {
    const el = document.querySelector<HTMLElement>(`[data-mi="${mi}"][data-p="${page}"]`)
    if (!el) return
    const box = el.getBoundingClientRect()
    const target = window.scrollY + box.top + box.height * topY - window.innerHeight * VIEWPORT_HEADROOM_RATIO
    window.scrollTo({ top: Math.max(0, target), behavior: 'smooth' })
  }, PAGE_TOP_DELAY_MS)
}
