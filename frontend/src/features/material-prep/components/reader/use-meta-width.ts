import { useCallback, useEffect, useRef, useState } from 'react'

/** 右栏宽度的 localStorage 键（跨会话保留：律师的屏幕与阅读习惯是稳定的） */
const KEY = 'mp.meta.width'

/** 默认宽（与改动前的固定值一致，老用户升级后观感不变） */
export const META_DEFAULT_WIDTH = 256
/** 窄屏（@min-[1280px]）下的默认宽 */
export const META_WIDE_DEFAULT = 296

export const META_MIN_WIDTH = 220
export const META_MAX_WIDTH = 640

function clamp(v: number): number {
  return Math.min(META_MAX_WIDTH, Math.max(META_MIN_WIDTH, Math.round(v)))
}

/** 读档：localStorage 不可用（隐私模式 / SSR）时退回默认值，绝不抛。 */
export function readMetaWidth(): number | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const n = Number(raw)
    return Number.isFinite(n) ? clamp(n) : null
  } catch {
    return null
  }
}

/**
 * 右栏宽度 + 拖拽改宽。
 *
 * ## 为什么拖拽手柄放在右栏左缘
 *
 * 右栏贴屏幕右缘，把手放它右边在物理上不可达。放左缘（也就是中栏与右栏的接缝）
 * 拖拽方向与视觉直觉一致：往左拖变宽、往右拖变窄。
 *
 * ## 为什么宽度记 localStorage 而不是进 store/草稿
 *
 * 它是**纯显示偏好**：与具体材料包无关、不该进 Undo 栈、不该随草稿同步给后端。
 * 换一个材料包打开阅读器，栏宽保持原样才是符合直觉的行为。
 *
 * ## 拖拽期间不写 localStorage
 *
 * pointermove 每帧都写会在拖动时产生几百次同步 IO（localStorage 是阻塞的），
 * 大 width 下能明显拖慢渲染。改为拖拽期间只更新 state，pointerup 落一次盘。
 */
export function useMetaWidth(narrow: boolean) {
  // 初始值：存档优先；没有存档时给默认（窄屏抽屉另有一套固定宽，由 CSS 管）
  const [width, setWidth] = useState<number>(() => readMetaWidth() ?? (narrow ? META_WIDE_DEFAULT : META_DEFAULT_WIDTH))
  const draggingRef = useRef(false)
  const startRef = useRef({ x: 0, w: 0 })

  const persist = useCallback((w: number) => {
    try {
      localStorage.setItem(KEY, String(w))
    } catch {
      // 隐私模式/配额满：宽度只在本次会话生效，不影响使用
    }
  }, [])

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault()
      draggingRef.current = true
      startRef.current = { x: e.clientX, w: width }
      try {
        ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
      } catch {
        /* noop */
      }
    },
    [width],
  )

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!draggingRef.current) return
    // 往左拖 → 变宽，所以取差值取反
    setWidth(clamp(startRef.current.w + (startRef.current.x - e.clientX)))
  }, [])

  const endDrag = useCallback(
    (e: React.PointerEvent) => {
      if (!draggingRef.current) return
      draggingRef.current = false
      try {
        ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
      } catch {
        /* noop */
      }
      // 落盘：用函数式读最新值，避免闭包里拿到拖拽起始的旧 width
      setWidth((w) => {
        persist(w)
        return w
      })
    },
    [persist],
  )

  // 窄屏走抽屉，宽度由抽屉 CSS 决定（固定 296），拖拽手柄此时不渲染
  useEffect(() => {
    if (narrow) return
  }, [narrow])

  return { width, onPointerDown, onPointerMove, endDrag, dragging: draggingRef }
}
