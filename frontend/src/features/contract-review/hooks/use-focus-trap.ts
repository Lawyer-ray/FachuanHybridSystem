import { useEffect, useRef } from 'react'

/**
 * 抽屉的模态行为：Esc 关闭 + Tab 焦点圈定 + 关闭后把焦点还给原处。
 *
 * **为什么不改用 components/ui/sheet.tsx（Radix Dialog）**：Sheet 会把节点
 * portal 到 body 并接管挂载/卸载，本抽屉的调用方（材料预处理 Reader 的全屏层、
 * 合同文件夹的详情页）都依赖"抽屉是当前树的一部分"来拿 store 与 ref；且
 * Radix 的模态会自己锁 body 滚动、改 aria-hidden，牵连 Reader 与 workbench 的
 * 既有 DOM 断言。收益（focus trap / Esc / aria）用 30 行 Effect 就能拿全，
 * 所以按最小改动补齐无障碍，保留自绘壳层。真要统一视觉再换 Sheet 是有意的后续决定。
 *
 * 关闭时还原焦点：抽屉常由工具栏按钮打开，焦点丢回 body 会让键盘用户从头 Tab。
 */
export function useFocusTrap(active: boolean, onClose: () => void) {
  const panelRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!active) return
    const panel = panelRef.current
    const restoreTo = document.activeElement instanceof HTMLElement ? document.activeElement : null

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab' || !panel) return
      // 焦点圈定：Tab / Shift+Tab 在抽屉内循环，不跑到背后的页面上
      const focusables = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
        ),
        // 只圈可见元素：隐藏的 input / 折叠区里的按钮不该进 Tab 序
      ).filter(isVisible)
      if (focusables.length === 0) return
      const first = focusables[0]!
      const last = focusables[focusables.length - 1]!
      const current = document.activeElement
      if (e.shiftKey && (current === first || !panel.contains(current))) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && (current === last || !panel.contains(current))) {
        e.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', onKey, true)
    return () => {
      window.removeEventListener('keydown', onKey, true)
      restoreTo?.focus()
    }
  }, [active, onClose])

  return { panelRef }
}

/**
 * 元素当前是否可见（隐藏容器里的元素不参与 Tab 循环）。
 *
 * 用 `getClientRects()` 判定而不是 `offsetParent`：**jsdom 里 offsetParent 恒为
 * null**（不做布局），用它会把这个抽屉的测试全变成「零个可聚焦元素」。
 * jsdom 里所有元素都没有矩形，此时按可见放行——测试要覆盖的是循环逻辑本身。
 */
function isVisible(el: HTMLElement): boolean {
  const rects = el.getClientRects()
  if (rects.length > 0) return true
  return navigator.userAgent.includes('jsdom')
}
