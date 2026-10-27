import { useReaderStoreFields } from './use-reader-store-fields'

/**
 * 退出取字 / 选页提示条。
 *
 * 口径与 use-reader-keys 的 Esc 一致：取字态清掉待确认 OCR 与取字目标；
 * 选页态清选区并退出模式。HintBar 的退出按钮与 Esc 走同一条路径，
 * 免得两个入口各写一份、久了只改一处。
 */
export function useReaderHintExit() {
  const { pickInfo, setOcrPending, setPickInfo, clearSel, toggleSelMode } = useReaderStoreFields()
  return () => {
    if (pickInfo >= 0) {
      setOcrPending(null)
      setPickInfo(-1)
      return
    }
    clearSel()
    toggleSelMode()
  }
}
