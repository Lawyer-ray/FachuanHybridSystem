import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ShieldAlert } from 'lucide-react'

import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

import { listPending } from './api'
import { PendingRuns } from './PendingRuns'

/**
 * 材料准备页顶部的**全局**待核对入口。
 *
 * ## 为什么要有它
 *
 * 检出红线后，结论只躺在「归案 → 选中既有案件」那个弹窗里——律师不去归案就永远
 * 看不到。这一处把「还有多少回传件等着裁决」搬到律师每天都会经过的页面上。
 *
 * ## 为什么是常驻一行、而不是只在有货时才出现
 *
 * 只在有货时出现，等于律师永远不知道该不该找它；常驻一行（0 时是灰的正常态）让他
 * 形成「这里会告诉我有没有事」的预期。0 时不可点，避免点开一个空弹窗。
 *
 * ## 为什么数据取 `listPending()` 而不是按案查
 *
 * 这一层不知道（也不该知道）当前在办哪个案子；后端按可见性收窄，前端只负责显示。
 */
export function PendingEntry() {
  const [open, setOpen] = useState(false)
  const { data } = useQuery({
    queryKey: ['doc-verify-pending-entry'],
    queryFn: ({ signal }) => listPending(50, signal),
    // 后台切回来时刷新一次即可：这是「有没有事」的提示，不需要秒级轮询
    refetchOnWindowFocus: true,
  })
  const count = data?.length ?? 0

  return (
    <>
      <div className="flex items-center justify-end">
        <button
          type="button"
          onClick={() => count > 0 && setOpen(true)}
          disabled={count === 0}
          aria-label={count > 0 ? `回传件待核对 ${count} 份` : '没有待核对的回传件'}
          className={cn(
            'flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] transition-colors',
            count > 0
              ? 'border-status-red/30 bg-status-red-bg font-medium text-status-red hover:bg-status-red-bg/70'
              : 'cursor-default border-border text-muted-foreground',
          )}
        >
          <ShieldAlert className="h-3.5 w-3.5" />
          回传件待核对
          <span className="tabular-nums">{count}</span>
          {count > 0 && <ChevronRight className="h-3.5 w-3.5" />}
        </button>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-2xl">
          <DialogTitle>回传件待核对</DialogTitle>
          <DialogDescription>
            客户回传件与出站基线不一致、或无法核对的那些件。采纳/退回都会留痕。
          </DialogDescription>
          <div className="mt-3">
            <PendingRuns />
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
