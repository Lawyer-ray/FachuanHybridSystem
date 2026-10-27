import { useEffect } from 'react'
import { useReader } from '../../store'

/**
 * 阅读器全局键位：
 *   - Esc 逐级退出（OCR 待确认 → 选页模式 → 有选页 → 取字态 → 关闭阅读器）
 *   - S（无修饰键）合并当前选中页
 * 输入框内不劫持。直读 store.getState()，不随状态重建 listener。
 *
 * 归案弹窗（AssignModal）**不在这条 Esc 栈里**：它已改成 Radix Dialog，Esc 由
 * Radix 的 DismissableLayer 自己处理（该监听挂在 document 上，按下时就把
 * defaultPrevented 置真，本 hook 在这里直接让路）。因此不能再判 store 的
 * assignOpen —— 那会和 Radix 形成双重关闭（Radix 关一次、这里再关一次，
 * 后者还会顺手把阅读器关掉）。
 */
export function useReaderKeys() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t && t.closest && t.closest('input, textarea, select')) return
      const s = useReader.getState()
      if (e.key === 'Escape') {
        // 已被更上层的弹层（Radix Dialog 的 Esc 关闭）消费：让路，不越级关阅读器
        if (e.defaultPrevented) return
        e.preventDefault()
        if (s.ocrPending) {
          s.setOcrPending(null)
          s.setPickInfo(-1)
        } else if (s.selMode) {
          s.clearSel()
          s.toggleSelMode()
        } else if (s.selPages.length) {
          s.clearSel()
        } else if (s.pickInfo >= 0) {
          s.setPickInfo(-1)
        } else {
          s.close()
        }
        return
      }
      if ((e.key === 's' || e.key === 'S') && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) {
        if (s.selPages.length) {
          e.preventDefault()
          s.applySel()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
