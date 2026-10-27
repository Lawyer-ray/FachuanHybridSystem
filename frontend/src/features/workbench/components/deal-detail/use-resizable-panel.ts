import { useCallback, useEffect, useState } from 'react'

import { useElementWidth } from '@/hooks/use-element-width'
import { beginDrag } from '@/lib/drag-listeners'

/**
 * 可拖拽的分栏宽度（记住用户偏好）。
 *
 * **为什么让用户自己拖**：右栏装什么差别很大——只有事实卡时 360px 够用；
 * 一旦在预览 OnlyOffice，A4 正文需要 700px 以上才不缩字。写死断点只能猜一个
 * 折中值，而每个律师的屏幕、缩放、阅读习惯都不同。给一条可拖的分隔条，
 * 他自己调到舒服为止，下次打开还记得。
 *
 * **为什么记 localStorage 而不是后端**：这是「这台设备的窗口布局」，换电脑
 * 不该跟着走；也不必为此加一次写库。
 */
/**
 * 左栏最小宽度。
 *
 * 服务事项表有日期 116 + 类型 68 + 状态 84 三个定宽列（268px），再加上
 * 「事项」「交付物」两列至少要各留 130 才能容下中文标题——低于 560 就会
 * 挤成逐字竖排。
 */
const LEFT_MIN = 560

export function useResizablePanel({
  storageKey,
  defaultWidth,
  min = 320,
  /** 上限按视口比例算：屏幕小的时候给 1040 会挤没左栏 */
  maxRatio = 0.62,
  /** 从右边往左拖（右侧面板），所以宽度 = 容器右缘 - 指针 x */
  side = 'right',
}: {
  storageKey: string
  defaultWidth: number
  min?: number
  maxRatio?: number
  side?: 'right' | 'left'
}) {
  const [width, setWidthState] = useState<number>(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      const n = raw ? Number(raw) : NaN
      return Number.isFinite(n) && n > 0 ? n : defaultWidth
    } catch {
      return defaultWidth
    }
  })
  const [dragging, setDragging] = useState(false)
  /**
   * 容器实际宽度：竖排（窄屏）时页面不允许横向拖拽，宽度必须失效。
   *
   * localStorage 里记的可能是宽屏下拖出来的 900px，换到 800px 窗口后仍会
   * 按 900 渲染 → 右栏撑爆容器、左栏被挤没（实测容器 740、右栏 900）。
   *
   * 量宽不再自己 new ResizeObserver：用全局 useElementWidth（只量 clientWidth，
   * 比 window.resize 准、侧栏折叠等改变可用宽度的操作也能捕捉），它带
   * `typeof ResizeObserver === 'undefined'` 降级，jsdom 下不装桩也不炸。
   * callback ref 还给「有预览 / 无预览」是不同 DOM 节点的情况兜底（见下）。
   */
  const [setContainerRef, measuredWidth, containerEl] = useElementWidth<HTMLDivElement>()
  // 未挂载时为 0，对外仍报 null（页面靠 null 判断「首帧不算竖排」）
  const containerWidth = measuredWidth > 0 ? measuredWidth : null
  /**
   * 用户是否手动拖过。
   *
   * 没拖过时宽度按容器比例自适应（左栏永远留够宽度）；一旦手动拖过就以
   * 用户的选择为准并记住。否则「默认 720px」这种绝对像素在 1280 屏上会把
   * 左栏压到 472px——事项与交付物两列各 102px，中文必然挤成竖排。
   */
  const [userAdjusted, setUserAdjusted] = useState<boolean>(() => {
    try {
      return localStorage.getItem(storageKey) !== null
    } catch {
      return false
    }
  })

  // 拖拽期间外壳（禁选中 + 光标 + iframe 让出指针）与监听全交给 beginDrag，
  // 它会在 pointerup / pointercancel / 卸载时复位到原值。
  const startDrag = useCallback(() => {
    // 拖拽期间禁选中、改光标、让 iframe 让出指针（OnlyOffice 是个 iframe，
    // 指针划过去时它会截获事件，拖动会「断」在半路）。pointercancel 也收，
    // 否则触摸被打断时 userSelect: none 残留、拖拽态卡死。
    return beginDrag(
      (e) => {
        const box = containerEl?.getBoundingClientRect()
        if (!box) return
        const raw = side === 'right' ? box.right - e.clientX : e.clientX - box.left
        const max = Math.max(min, box.width * maxRatio)
        setWidthState(Math.round(Math.min(max, Math.max(min, raw))))
        setUserAdjusted(true)
      },
      () => setDragging(false),
      { blockIframes: true },
    )
  }, [containerEl, min, maxRatio, side])

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    setDragging(true)
    // target 可能不是元素（合成事件/测试替身）：拿不到就不捕获，
    // 指针事件仍走 window 监听，拖动照样能用
    const el = e.target as HTMLElement | null
    el?.setPointerCapture?.(e.pointerId)
  }, [])

  useEffect(() => {
    if (!dragging) return
    return startDrag()
  }, [dragging, startDrag])

  // 落盘只在松手后：拖动过程中每帧写 localStorage 会明显卡
  useEffect(() => {
    if (dragging) return
    try {
      localStorage.setItem(storageKey, String(width))
    } catch {
      // 隐私模式/配额满：记不住就算了，不影响本次使用
    }
  }, [dragging, storageKey, width])

  /** 键盘调整用：支持函数式更新（与 setState 同形） */
  const setWidth = useCallback((next: number | ((w: number) => number)) => {
    setWidthState((prev) => {
      const v = typeof next === 'function' ? next(prev) : next
      setUserAdjusted(true)
      const box = containerEl?.getBoundingClientRect()
      // 容器还没挂载（首帧）时只钳 min，不钳 max——否则 max 缺失会让
      // Math.min 把值放到 v 本身，min 也随之失效
      const clampedToMin = Math.max(min, v)
      const max = box ? Math.max(min, box.width * maxRatio) : Number.POSITIVE_INFINITY
      return Math.round(Math.min(max, clampedToMin))
    })
  }, [containerEl, min, maxRatio])

  /**
   * 容器能给的硬上限：两个约束取小。
   *
   * - `hardMax`：右栏最多占容器 maxRatio（默认 68%），否则左栏被压没
   * - `keepLeftMin`：右栏宽度不超过「容器 − 左栏下限」，保证事项表放得下
   *
   * **用户拖过的宽度也必须受它约束**：localStorage 记的是「当时那个窗口」
   * 拖出来的值，换到更窄的窗口后照用会把容器撑爆（实测：存 1140 换到
   * 1400 屏，左栏只剩 174px、事项/交付物两列归零、中文逐字竖排）。
   */
  const hardMax =
    containerWidth === null ? Number.POSITIVE_INFINITY : Math.max(min, containerWidth * maxRatio)
  const keepLeftMin =
    containerWidth === null ? Number.POSITIVE_INFINITY : Math.max(min, containerWidth - LEFT_MIN)
  const capped = Math.min(hardMax, keepLeftMin)

  /** 没手动拖过时按容器给宽度（不留多余空白，也不挤左栏） */
  const autoWidth = containerWidth === null ? width : Math.round(capped)

  // 用户拖过的值优先，但仍要夹在容器允许的范围内
  const clampedUserWidth = Math.min(width, capped)
  const effective = userAdjusted ? clampedUserWidth : autoWidth

  /**
   * 是否竖排（上下堆叠）：看**容器本身**是否窄于页面的竖排断点。
   *
   * 之前写成 `containerWidth < Math.min(effective, 1100)`——拿容器和面板宽度比，
   * 而面板宽度本来就小于容器，于是恒为 false，竖排判定永不成立（实测 800px
   * 窄屏下分隔条仍然显示、拖拽态也失效）。
   */
  const stacked = containerWidth !== null && containerWidth < 1100

  return {
    width: stacked ? undefined : effective,
    /** 真实生效的宽度（竖排时 undefined） */
    effectiveWidth: stacked ? undefined : effective,
    stacked,
    dragging,
    /** 容器 ref（useElementWidth 的 callback ref，用法与 ref 一致） */
    containerRef: setContainerRef,
    onPointerDown,
    setWidth,
    /**
     * 容器实测宽度（ResizeObserver，含并排 AI 面板让位后的净宽；未挂载为 null）。
     * 页面用它驱动自己的横/竖排（见 NonLitDetailPage 的「文档对照」说明）——
     * 视口媒体查询量不到 AI 面板吃掉的宽度，量错了就会出现「预览栏横排自然宽、
     * 左栏被挤成逐字竖排」的破版。
     */
    containerWidth,
  }
}
