import { useEffect, useState } from 'react'

/**
 * 防抖值：输入停 delayMs 后才更新为最新值。
 *
 * typeahead 检索的标准姿势——raw 值喂输入框（UI 即时响应），防抖值进
 * queryKey（输入停顿后才真正打后端），避免每个按键一次请求。
 * 首帧直接以初始值返回（挂载即拉一版初始列表的场景不受影响）。
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    // 值没变不重挂计时器；变更后停满 delayMs 才落防抖值，中途再变即作废重计
    const t = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(t)
  }, [value, delayMs])

  return debounced
}
