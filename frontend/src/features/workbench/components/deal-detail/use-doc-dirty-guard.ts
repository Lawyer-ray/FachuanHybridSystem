import { useCallback, useRef, useState } from 'react'

/**
 * 「画布里有未保存的修改」时，把破坏性导航拦下来问一句。
 *
 * 用法：所有会**换掉或关掉**当前文档的动作都走 `guard(action)`，而不是直接执行。
 *
 * ```ts
 * const doc = useDocDirtyGuard()
 * const closePreview = () => doc.guard(() => setPicked(null))
 * const openFile = (f) => doc.guard(() => setPicked(f))
 * // 页面上渲染 <UnsavedChangesDialog open={doc.pending} onStay={doc.stay} onLeave={doc.leave} />
 * ```
 *
 * **为什么用 ref 存脏标记**：拦的是「点下去那一刻」的状态，而 `guard()` 常在事件
 * 回调里同步调用；靠 state 会读到上一轮渲染的旧值，第一次点击永远漏拦。
 *
 * **为什么把待执行动作存进 state 而不是立刻执行**：确认弹窗是异步的，动作必须
 * 留到用户点了「放弃修改」再跑；`setPending(() => run)` 是 React 里存函数的标准写法
 * （直接 `setPending(run)` 会被当成 updater 立即调用）。
 */
export function useDocDirtyGuard() {
  const dirtyRef = useRef(false)
  const [dirty, setDirty] = useState(false)
  const [pending, setPending] = useState<(() => void) | null>(null)

  /** 由文档卡回报（画布进入/退出「改了但没存」） */
  const markDirty = useCallback((next: boolean) => {
    dirtyRef.current = next
    setDirty(next)
  }, [])

  /** 包一层：脏就弹确认，不脏就直接执行 */
  const guard = useCallback((run: () => void) => {
    if (!dirtyRef.current) {
      run()
      return
    }
    setPending(() => run)
  }, [])

  /** 放弃修改，继续原本的动作 */
  const leave = useCallback(() => {
    const run = pending
    dirtyRef.current = false
    setDirty(false)
    setPending(null)
    run?.()
  }, [pending])

  /** 继续编辑 */
  const stay = useCallback(() => setPending(null), [])

  return { dirty, markDirty, guard, pending: pending !== null, leave, stay }
}
