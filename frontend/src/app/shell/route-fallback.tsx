/**
 * 路由级懒加载 fallback：与各页面的 loading 分支同风格（居中细 spinner）。
 *
 * 单独成文件是为了打断 `app/router.tsx <-> app/shell/AppShell.tsx` 的静态循环：
 * AppShell 需要这个叶子 UI，router 需要 AppShell，二者原先互相 import。
 *
 * 块本身不在这里手写：走 `LoadingBlock`（`components/shared/AsyncState`）这个
 * 三态单一来源，顺带拿到 `role="status"` / `aria-live="polite"`（转圈时要让读屏
 * 播报「正在加载」，此前手写的 div 没有这两个属性）。
 */
import { LoadingBlock } from '@/components/shared/AsyncState'

export function RouteFallback() {
  // py-24 / text-secondary-foreground 覆盖 LoadingBlock 的默认 py-8 / muted 色，
  // 与改造前视觉一致（字号本就是同档 text-sm）。
  return <LoadingBlock text="正在加载…" className="py-24 text-secondary-foreground" />
}
