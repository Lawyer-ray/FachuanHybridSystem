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
      const box = containerRef.current?.getBoundingClientRect()
      // 容器还没挂载（首帧）时只钳 min，不钳 max——否则 max 缺失会让
      // Math.min 把值放到 v 本身，min 也随之失效
      const clampedToMin = Math.max(min, v)
      const max = box ? Math.max(min, box.width * maxRatio) : Number.POSITIVE_INFINITY
      return Math.round(Math.min(max, clampedToMin))
    })
  }, [min, maxRatio])

  return { width, dragging, containerRef, onPointerDown, setWidth }
}
