/**
 * 输入法（IME）Enter 守卫：把「选词时的 Enter」和「真的要发送的 Enter」分开。
 *
 * 典型事故：WebKit 与部分中文输入法**先派发 compositionend、再派发同一次选词
 * Enter 的 keydown**。此时 `nativeEvent.isComposing` 已经是 false，只看这个标志
 * 的发送逻辑会把选词那次 Enter 当发送，把半句话直接发出去。
 *
 * 三重判定「正在合成」：
 *   1. composingRef（compositionstart/end 区间内）——事件顺序不可靠时的主依据；
 *   2. `event.nativeEvent.isComposing`——标准标志；
 *   3. `event.keyCode === 229`——老 WebKit 在合成期间把 keyCode 钉成 229，
 *      而某些输入法干脆不派发 composition 事件，只剩这一条可依。
 *
 * 为什么还要「人為 80ms 窗口」：compositionend 之后紧跟的那一次 Enter 才是选词
 * 确认键，而**用户事后真按的 Enter 已经是另一次事件**，落在这个窗口外。所以窗口
 * 只覆盖紧邻事件，正常用户再按一次 Enter 不受影响（窗口取 80ms：既覆盖 WebKit
 * 同一任务内的背靠背派发，又远小于人的二次按键间隔）。
 *
 * 为什么用 `event.timeStamp` 而不是 `Date.now()`：timeStamp 与 compositionend 的
 * timeStamp 是同一事件循环口径（同一个 monotonic 时钟），不受系统时间被调整
 * （NTP 校时、改时区、休眠唤醒）影响，也不会因两次取值之间的事件循环延迟而抖动；
 * 拿 Date.now() 与 timeStamp 混算会得到一个语义错的差。
 *
 * 用 useRef 不用 state：合成状态变了不该触发重渲染（textarea 的几百次合成
 * 不该带动整个 Composer 树重渲染），回调返回布尔值由调用方自己决定短路。
 */

import { useCallback, useRef } from 'react'

/** compositionend 之后多久内的 Enter 仍算「选词确认」，需要吞掉（毫秒） */
export const POST_COMPOSITION_ENTER_GUARD_MS = 80

/** 本 hook 只关心 Enter 判定和 composition 生命周期，不绑定具体 DOM 元素 */
type KeyLikeEvent = Pick<KeyboardEvent, 'key'> & {
  timeStamp?: number
  keyCode?: number
  nativeEvent?: { isComposing?: boolean }
}

/** guardEnter 需要能吞掉默认行为，故这里要求 preventDefault 一定存在 */
type GuardableEvent = KeyLikeEvent & Pick<KeyboardEvent, 'preventDefault'>

export function useImeEnterGuard() {
  /** 是否处在 compositionstart → compositionend 区间内 */
  const composingRef = useRef(false)
  /** 最近一次 compositionend 的事件时间戳（null = 从没合成过 / 已被 start 清掉） */
  const compositionEndedAtRef = useRef<number | null>(null)

  /** 三重判定：ref / 标准 isComposing 标志 / 老 WebKit 的 keyCode 229 */
  const isComposing = useCallback((event?: KeyLikeEvent) => {
    if (composingRef.current) return true
    if (event?.nativeEvent?.isComposing === true) return true
    return event?.keyCode === 229
  }, [])

  const shouldIgnoreEnter = useCallback(
    (event: KeyLikeEvent) => {
      if (event.key !== 'Enter') return false
      if (isComposing(event)) return true
      const endedAt = compositionEndedAtRef.current
      if (endedAt === null) return false
      const delta = (event.timeStamp ?? 0) - endedAt
      // 负值（事件早于 compositionend，例如缺失 timeStamp 落到 0）不属于尾随
      // 窗口：那个 Enter 发生在合成之内，归 composingRef / keyCode 229 管；
      // 在这里一并吞掉反而会误伤「合成结束后用户立刻正常按的 Enter」
      return delta >= 0 && delta <= POST_COMPOSITION_ENTER_GUARD_MS
    },
    [isComposing],
  )

  /**
   * 判定并处理 Enter：
   * - 返回 false 表示「不是需要吞掉的 Enter」，调用方照常处理（发送 / 换行）；
   * - 合成中的 Enter 只返回 true **不** preventDefault —— 交给输入法自己处理，
   *   我们抢了 preventDefault 会打断选词上屏；
   * - compositionend 后的尾随 Enter 是选词确认，调用方大概率已经写好了
   *   「Enter 即发送」，必须 preventDefault 吞掉默认行为。
   */
  const guardEnter = useCallback(
    (event: GuardableEvent) => {
      if (!shouldIgnoreEnter(event)) return false
      if (!isComposing(event)) event.preventDefault()
      return true
    },
    [isComposing, shouldIgnoreEnter],
  )

  const onCompositionStart = useCallback(() => {
    composingRef.current = true
    // 清掉上一次的窗口：否则上一轮 compositionend 留下的时间戳可能把
    // 这一轮刚开始时用户的一次正常 Enter 也吞进去
    compositionEndedAtRef.current = null
  }, [])

  const onCompositionEnd = useCallback((event: Pick<Event, 'timeStamp'>) => {
    composingRef.current = false
    compositionEndedAtRef.current = event.timeStamp
  }, [])

  return {
    onCompositionStart,
    onCompositionEnd,
    isComposing,
    shouldIgnoreEnter,
    guardEnter,
  }
}
