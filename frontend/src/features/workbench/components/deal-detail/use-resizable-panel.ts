import { useCallback, useEffect, useRef, useState } from 'react'

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
export function useResizablePanel({
  storageKey,
  defaultWidth,
  min = 320,
  layoutKey = '',
  /** 上限按视口比例算：屏幕小的时候给 1040 会挤没左栏 */
  maxRatio = 0.62,
  /** 从右边往左拖（右侧面板），所以宽度 = 容器右缘 - 指针 x */
  side = 'right',
}: {
  storageKey: string
  defaultWidth: number
  /** 布局变化时重新量容器（如「有预览 ↔ 无预览」切换了 DOM 结构） */
  layoutKey?: string | number
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
   */
  const [containerWidth, setContainerWidth] = useState<number | null>(null)
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

  // 拖拽期间禁掉文本选择与 iframe 事件吞噬（OnlyOffice 是个 iframe，
  // 指针划过去时它会截获 mousemove，拖动会「断」在半路）
  useEffect(() => {
    if (!dragging) return
    const prevSelect = document.body.style.userSelect
    const prevCursor = document.body.style.cursor
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'

    const frames = Array.from(document.querySelectorAll('iframe'))
    const prevEvents = frames.map((f) => f.style.pointerEvents)
    // 关键：拖拽时让 iframe 不接收指针事件，否则光标一进画布就丢 mousemove
    frames.forEach((f) => (f.style.pointerEvents = 'none'))

    return () => {
      document.body.style.userSelect = prevSelect
      document.body.style.cursor = prevCursor
      frames.forEach((f, i) => (f.style.pointerEvents = prevEvents[i] ?? ''))
    }
  }, [dragging])

  const containerRef = useRef<HTMLDivElement>(null)

  // 量容器宽度：窗口尺寸变化时同步（ResizeObserver 比 window.resize 准，
  // 侧栏折叠等改变可用宽度的操作它也能捕捉到）。
  //
  // 依赖 layoutKey：页面在「有预览 / 无预览」时容器可能是不同 DOM 节点
  // （flex vs grid），只跑一次的 effect 会量到已经卸载的那个、拿到 null。
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width
      if (typeof w === 'number') setContainerWidth(w)
    })
    ro.observe(el)
    setContainerWidth(el.getBoundingClientRect().width)
    return () => ro.disconnect()
  }, [layoutKey])

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

    const onMove = (e: PointerEvent) => {
      const box = containerRef.current?.getBoundingClientRect()
      if (!box) return
      const raw =
        side === 'right' ? box.right - e.clientX : e.clientX - box.left
      const max = Math.max(min, box.width * maxRatio)
      setWidthState(Math.round(Math.min(max, Math.max(min, raw))))
      setUserAdjusted(true)
    }
    const onUp = () => setDragging(false)

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
    }
  }, [dragging, min, maxRatio, side])

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
      const box = containerRef.current?.getBoundingClientRect()
      // 容器还没挂载（首帧）时只钳 min，不钳 max——否则 max 缺失会让
      // Math.min 把值放到 v 本身，min 也随之失效
      const clampedToMin = Math.max(min, v)
      const max = box ? Math.max(min, box.width * maxRatio) : Number.POSITIVE_INFINITY
      return Math.round(Math.min(max, clampedToMin))
    })
  }, [min, maxRatio])

  /**
   * 窄屏（竖排）时不要固定宽度。
   *
   * 阈值与页面的竖排断点一致（1100/1024）：一旦上下堆叠，左右分栏的宽度就
   * 没有意义，继续用 900px 会把容器撑爆。取容器 90% 作为下限判断，
   * 避免「容器比记住的宽度还窄」时溢出。
   */
  /**
   * 没手动拖过时按容器比例给宽度。
   *
   * **要点是给左栏留够**：左栏放的是服务事项表（日期 116 + 类型 68 + 状态 84
   * 三个定宽列就 268px，再加事项与交付物两列），低于 460px 中文就会被挤成
   * 竖排。所以右栏宽度 = 容器 - 左栏最小宽，而不是「容器 × 某个比例」——
   * 后者在宽屏会把右栏撑得过大、左栏照样不够。
   */
  const LEFT_MIN = 560
  const autoWidth =
    containerWidth === null
      ? width
      : Math.round(
          Math.min(
            // 右栏天花板：容器 68%（留给左栏 32%）
            Math.max(min, containerWidth * maxRatio),
            // 右栏按「容器减左栏下限」给，宽屏下右栏才能长起来
            Math.max(min, containerWidth - LEFT_MIN),
          ),
        )
  const effective = userAdjusted ? width : autoWidth

  const stacked = containerWidth !== null && containerWidth < Math.min(effective, 1100)

  return {
    width: stacked ? undefined : effective,
    /** 真实生效的宽度（竖排时 undefined） */
    effectiveWidth: stacked ? undefined : effective,
    stacked,
    dragging,
    containerRef,
    onPointerDown,
    setWidth,
  }
}
