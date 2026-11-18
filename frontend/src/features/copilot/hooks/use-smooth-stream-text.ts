/**
 * 流式文本平滑放字：把「全量文本」渲染成一条按节拍追赶的可见前缀。
 *
 * `MessageList` 原来把 `message.content` 直接交给 `<ReactMarkdown>`，token
 * 一来就整篇重解析，网络抖动时还会顿一下。这里给可见文本加一层节流：
 * 每 `SMOOTH_STREAM_TICK_FRAMES` 帧才放一次字（切点由纯函数
 * `nextStreamCut` 决定，见 lib/smooth-stream.ts）。
 *
 * **硬不变量：任何时刻返回值都是 `full` 的前缀。** 违反它 markdown 会原地
 * 重排（甚至把表格结构打乱），视觉上比不平滑更糟。因此只在
 * `full.startsWith(displayed)` 成立时才逐拍推进；一旦前缀关系被破坏
 * （快照改写），立即放弃渐进、整段显示。
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import {
  SMOOTH_STREAM_JUMP_BACKLOG,
  SMOOTH_STREAM_MAX_LENGTH,
  SMOOTH_STREAM_TICK_FRAMES,
  nextStreamCut,
} from '../lib/smooth-stream'

/** 任一成立就直接显示全文：非直播 / 被快照改写 / 积压过大 / 全文过长 */
function shouldShowAll(full: string, displayed: string, active: boolean): boolean {
  return (
    !active ||
    !full.startsWith(displayed) ||
    full.length - displayed.length > SMOOTH_STREAM_JUMP_BACKLOG
  )
}

export function useSmoothStreamText(full: string, live: boolean): string {
  // 长回复不平滑：每拍重解析整段会掉帧，比不平滑还卡
  const active = live && full.length <= SMOOTH_STREAM_MAX_LENGTH
  const [displayed, setDisplayed] = useState(full)

  // 全文与可见文本的最新值给 rAF 循环读——循环不能随每段新字重建（见下）
  const fullRef = useRef(full)
  const displayedRef = useRef(displayed)

  // 用 layout effect 同步 ref：渲染里推导出的 visible 可能已经跳到全文
  // （积压超限 / 快照改写），若拖到普通 effect 再同步，下一拍就会拿旧值
  // 去切，可见文本倒退。
  useLayoutEffect(() => {
    fullRef.current = full
    displayedRef.current = displayed
  })

  const visible = shouldShowAll(full, displayed, active) ? full : displayed

  useEffect(() => {
    if (!active) return
    let raf = 0
    let frames = 0
    const loop = () => {
      frames += 1
      if (frames % SMOOTH_STREAM_TICK_FRAMES === 0) {
        const fullNow = fullRef.current
        const shownNow = displayedRef.current
        // 前缀关系被破坏时不要再切（切了也不是前缀），交给渲染期整段显示
        if (fullNow.length > shownNow.length && fullNow.startsWith(shownNow)) {
          const cut = nextStreamCut(fullNow, shownNow.length)
          if (cut > shownNow.length) setDisplayed(fullNow.slice(0, cut))
        }
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
    // 依赖数组只能有 active：随每段新字重启的话，字段来得比两帧密时永远
    // 数不到拍点（每次都从 frames=0 重新数），放字会被饿死。
    // 全文从 fullRef 读。
  }, [active])

  return visible
}
