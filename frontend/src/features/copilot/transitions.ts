/**
 * 会话内容切换的局部 crossfade（View Transition API）：从 store.ts 抽出的
 * 纯渲染辅助。回调里的状态变更会被浏览器捕捉为旧/新两帧，仅对带
 * view-transition-name 的消息区播放淡出淡入（见 copilot.css）。不支持的
 * 浏览器（或用户开了「减弱动态效果」）直接执行回调，无动画降级。
 */
import { flushSync } from 'react-dom'

export function withViewTransition(update: () => void): void {
  // node 测试环境 / SSR 无 document；不支持的浏览器降级为直接更新
  if (typeof document === 'undefined') {
    update()
    return
  }
  const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown }
  if (typeof doc.startViewTransition !== 'function' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    update()
    return
  }
  // 并发过渡（上一段 200ms 未播完、下一段又起）时浏览器会 skip 旧过渡，
  // 其 ready/finished promise 会被 reject——不接住会变成未处理的 rejection
  const transition = doc.startViewTransition(() => {
    flushSync(update)
  }) as { ready?: Promise<void>; finished?: Promise<void> }
  transition.ready?.catch(() => {})
  transition.finished?.catch(() => {})
}
