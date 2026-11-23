/**
 * 策展入口提示（仅本团队/律所管理员可见）：说明文案 + 「提炼为团队惯例」按钮。
 *
 * 从 `MemoryDrawer` 拆出（后者单函数超软红线）。是否显示由外壳按 `can_curate` 判定，
 * 本组件只管这一块的排版，不取数。
 */

import { Button } from '@/components/ui/button'

export function CuratePrompt({ onOpen }: { onOpen: () => void }) {
  return (
    <div className="mt-5 rounded-[10px] border border-border bg-secondary/30 px-3 py-2.5">
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        你是本团队/律所的管理员，可以把成员的高频记忆提炼为团队级惯例（需改写脱敏，不会原样共享）。
      </p>
      <Button size="sm" variant="secondary" className="mt-2 h-7 px-2.5 text-[11px]" onClick={onOpen}>
        提炼为团队惯例
      </Button>
    </div>
  )
}
