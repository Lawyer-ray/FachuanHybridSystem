import { useState } from 'react'
import { Search } from 'lucide-react'

import { contractHint } from '../domain'
import { useSelectableContracts } from '../hooks/use-selectable-contracts'
import { BTN_PRIMARY } from '@/components/shared/panel-styles'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

/**
 * 「换个项目」弹窗：搜索并选择一个项目，把当前这笔到账归到它名下。
 *
 * 下拉数据源是后端的 `selectable-contracts`，**已经过滤掉已收满/已归档/
 * 案件全结案**的项目——与自动匹配共用同一套资格规则。所以：
 * - 新建的合同只要合格就会自动出现在这里（用户要求）；
 * - 已收满的项目不会出现，避免用户选到一个系统永远不会推荐的项目。
 */
export function ProjectPicker({
  open,
  onOpenChange,
  initialKeyword = '',
  onPick,
  busy,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialKeyword?: string
  onPick: (contractId: number) => void
  busy: boolean
}) {
  const [keyword, setKeyword] = useState(initialKeyword)
  const [picked, setPicked] = useState<number | null>(null)
  const { data = [], isLoading, isError, error, refetch } = useSelectableContracts(keyword, open)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[560px]">
        <DialogHeader>
          <DialogTitle className="text-[15px]">换个项目</DialogTitle>
          <DialogDescription className="text-[12px]">
            只列出仍可收款的在办项目（已收满、已归档、案件已结案的不会出现）。
          </DialogDescription>
        </DialogHeader>

        <div className="relative mt-1">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            autoFocus
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索项目名称或建档号"
            className="h-8 pl-8 text-[12.5px]"
          />
        </div>

        <div className="mt-2 max-h-[320px] overflow-y-auto rounded-[8px] border border-border">
          {isLoading && <div className="px-3 py-6 text-center text-[12px] text-muted-foreground">正在载入…</div>}
          {isError && (
            <div className="px-3 py-6 text-center text-[12px] text-destructive">
              {errMessage(error, '项目列表加载失败')}
              <button type="button" className="ml-1.5 underline" onClick={() => void refetch()}>
                重试
              </button>
            </div>
          )}
          {!isLoading && !isError && data.length === 0 && (
            <div className="px-3 py-6 text-center text-[12px] text-muted-foreground">没有可收款的项目</div>
          )}
          {data.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setPicked(c.id)}
              className={cn(
                'flex w-full items-start gap-2 border-b border-border-light px-2.5 py-2 text-left transition-colors last:border-b-0 hover:bg-secondary/50',
                picked === c.id && 'bg-secondary',
              )}
            >
              <span
                className={cn(
                  'mt-[3px] h-3 w-3 flex-none rounded-full border',
                  picked === c.id ? 'border-foreground bg-foreground' : 'border-border',
                )}
                aria-hidden
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] font-medium">{c.name}</span>
                <span className="block truncate text-[10.5px] text-muted-foreground">{contractHint(c) || c.fee_mode}</span>
              </span>
            </button>
          ))}
        </div>

        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="rounded-[7px] px-3 py-[6px] text-[12.5px] text-muted-foreground transition-colors hover:text-foreground"
          >
            取消
          </button>
          <button
            type="button"
            disabled={picked == null || busy}
            onClick={() => picked != null && onPick(picked)}
            className={BTN_PRIMARY}
          >
            确认归属到该项目
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
