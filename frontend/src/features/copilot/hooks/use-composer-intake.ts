/**
 * 输入框草稿的两条外部写入通道：框选引用（挂引用卡）与选区预填（追加文字）。
 *
 * 从 Composer 拆出（后者超软红线）。两条都用 window 自定义事件而不是 store：
 * 输入框文本是本地草稿 state（用户正在打字时不该被全局状态覆盖），这里只做
 * 一次性的「塞进来」，不参与渲染派生。
 *
 * 框选引用另有挂载兜底：刚开面板时 Composer 还没订阅，事件可能已经派发过，
 * 所以挂载后主动 takePendingQuote 取一次（两条路径都取后即清，不会重复挂卡）。
 */

import { useEffect, type RefObject } from 'react'

import { COPILOT_PREFILL_EVENT, COPILOT_QUOTE_EVENT, clearPendingQuote, takePendingQuote } from '../launch'
import type { SelectionQuote } from '../types'

export function useComposerIntake({
  setText,
  setPendingQuote,
  textareaRef,
  autoGrow,
}: {
  setText: React.Dispatch<React.SetStateAction<string>>
  setPendingQuote: (quote: SelectionQuote | null) => void
  textareaRef: RefObject<HTMLTextAreaElement | null>
  /** 预填后要把框撑到新内容的高度 */
  autoGrow: () => void
}) {
  useEffect(() => {
    function onQuote(e: Event) {
      const q = (e as CustomEvent<SelectionQuote>).detail
      if (q?.text) setPendingQuote(q)
      clearPendingQuote()
    }
    window.addEventListener(COPILOT_QUOTE_EVENT, onQuote)
    const missed = takePendingQuote()
    if (missed?.text) setPendingQuote(missed)
    return () => window.removeEventListener(COPILOT_QUOTE_EVENT, onQuote)
    // setPendingQuote 是 zustand 稳定引用
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    function onPrefill(e: Event) {
      const d = (e as CustomEvent<{ text?: string }>).detail
      const t = d?.text?.trim()
      if (!t) return
      // 追加而不是覆盖：律师可能已经写了半句，别把他打的字冲掉
      setText((prev) => (prev.trim() ? `${prev.trim()}\n${t}` : t))
      requestAnimationFrame(() => {
        const el = textareaRef.current
        if (!el) return
        el.focus()
        el.setSelectionRange(el.value.length, el.value.length)
        autoGrow()
      })
    }
    window.addEventListener(COPILOT_PREFILL_EVENT, onPrefill)
    return () => window.removeEventListener(COPILOT_PREFILL_EVENT, onPrefill)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
