import { useCallback, useEffect, useRef, useState } from 'react'

import { copyText } from '@/lib/clipboard'

/**
 * 复制 + 短暂「已复制」反馈。
 *
 * 必须走 copyText（lib/clipboard）：它带非安全上下文的 execCommand 兜底。
 * 此前两处直接调 navigator.clipboard.writeText——内网 http 部署下
 * navigator.clipboard 是 undefined，可选链只挡住调用却留下空 promise，
 * 非可选链那处则直接抛 TypeError（点击复制按钮报错、没有任何反馈）。
 *
 * copied 到点自动复位；重复复制与卸载都要清定时器，否则上一次的复位计时
 * 会把刚置起的 true 提前打回 false（连点两下时「已复制」一闪就没）。
 */
export function useCopyFeedback(opts: { resetMs?: number } = {}) {
  const resetMs = opts.resetMs ?? 2000
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<number | null>(null)

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  // 卸载后回调可能还在飞行中（await copyText 期间用户离开了页面），
  // 这时再 setCopied 会告警；用挂载标记挡住。
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      clearTimer()
    }
  }, [clearTimer])

  const copy = useCallback(
    async (text: string): Promise<boolean> => {
      const ok = await copyText(text)
      if (!mountedRef.current) return ok
      if (!ok) {
        // 失败时不点亮「已复制」（会误导用户以为复制成功），失败提示交给调用方
        setCopied(false)
        clearTimer()
        return false
      }
      setCopied(true)
      clearTimer()
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null
        setCopied(false)
      }, resetMs)
      return true
    },
    [clearTimer, resetMs],
  )

  return { copied, copy }
}
