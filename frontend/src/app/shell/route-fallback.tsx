/**
 * 路由级懒加载 fallback：与各页面的 loading 分支同风格（居中细 spinner）。
 *
 * 单独成文件是为了打断 `app/router.tsx <-> app/shell/AppShell.tsx` 的静态循环：
 * AppShell 需要这个叶子 UI，router 需要 AppShell，二者原先互相 import。
 */
import { Loader2 } from 'lucide-react'

export function RouteFallback() {
  return (
    <div className="flex items-center justify-center gap-2 py-24 text-sm text-secondary-foreground">
      <Loader2 className="h-4 w-4 animate-spin" /> 正在加载…
    </div>
  )
}
