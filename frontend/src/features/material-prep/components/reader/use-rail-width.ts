import { useCallback, useRef, useState } from 'react'

/**
 * 左栏（材料目录）宽度 + 拖拽改宽。
 *
 * 与 `useMetaWidth`（右栏）是同一套范式，刻意不合并抽公共 hook：
 * 两者的**拖拽方向相反**（左栏往右拖变宽、右栏往左拖变宽），
 * 默认值、clamp 区间、localStorage 键也各自独立。硬抽一个带 direction 参数的
 * 公共 hook，只会让两处都多一层间接、少一分可读性。
 *
 * ## 为什么记 localStorage 而不是进 store/草稿
 *
 * 纯显示偏好：与具体材料包无关、不该进 Undo 栈、不该随草稿同步给后端。
 * 换一个材料包打开阅读器，栏宽保持原样才符合直觉。
 */

const KEY = 'mp.rail.width'

/** 默认宽（与改动前的固定值一致：窄屏 232 / 宽屏 268，老用户升级后观感不变） */
export const RAIL_DEFAULT_WIDTH = 232
export const RAIL_WIDE_DEFAULT = 268

/** 下限要放得下「段名 + 页数 + 类型」三行不换行；上限避免把中栏挤没 */
export const RAIL_MIN_WIDTH = 180
export const RAIL_MAX_WIDTH = 520

function clamp(v: number): number {
  return Math.min(RAIL_MAX_WIDTH, Math.max(RAIL_MIN_WIDTH, Math.round(v)))
}

/** 读档：localStorage 不可用（隐私模式 / SSR）时退回 null，由调用方给默认值。 */
export function readRailWidth(): number | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const n = Number(raw)
    return Number.isFinite(n) ? clamp(n) : null
  } catch {
    return null
  }
}

export function useRailWidth(wide: boolean) {
  const [width, setWidth] = useState<number>(() => readRailWidth() ?? (wide ? RAIL_WIDE_DEFAULT : RAIL_DEFAULT_WIDTH))
  const draggingRef = useRef(false)
  const startRef = useRef({ x: 0, w: 0 })

  const persist = useCallback((w: number) => {
    try {
      localStorage.setItem(KEY, String(w))
    } catch {
      // 隐私模式 / 配额满：宽度只在本次会话生效，不影响使用
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
    // 左栏贴屏幕左缘：往右拖 → 变宽，所以直接用差值（与右栏相反）
    setWidth(clamp(startRef.current.w + (e.clientX - startRef.current.x)))
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
      // 落盘：函数式读最新值，避免闭包里拿到拖拽起始的旧 width。
      // 拖拽期间不写盘（pointermove 每帧写 = 几百次同步 IO，会拖慢拖动）。
      setWidth((w) => {
        persist(w)
        return w
      })
    },
    [persist],
  )

  return { width, onPointerDown, onPointerMove, endDrag, dragging: draggingRef }
}
