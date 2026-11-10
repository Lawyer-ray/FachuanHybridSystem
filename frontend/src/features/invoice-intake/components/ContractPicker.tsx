import { useState } from 'react'
import { Search } from 'lucide-react'

import { useSelectableContracts } from '../hooks/use-selectable-contracts'
import { BTN_PRIMARY } from '@/components/shared/panel-styles'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

/**
 * 「换个项目」弹窗：搜索并选择项目，把当前这张发票改挂到它名下。
 *
 * 下拉数据源是后端的 `selectable-contracts`，按**发票口径**过滤（已收满的项目
 * 照样能选 —— 钱收齐才开票是正常顺序）。新建的合格合同会自动出现在这里。
 *
 * 项目一旦改判，收款预选就不再适用（预选是相对原建议合同算的），所以选完后
 * 确认动作只带 contract_id、不带 payment_id —— 发票先挂项目名下，之后在项目页
 * 关联具体收款。这一点必须让用户看见，否则会疑惑"怎么没挂到收款"。
 */
export function ContractPicker({
  open,
  onOpenChange,
  onPick,
  busy,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onPick: (contractId: number) => void
  busy: boolean
}) {
  const [keyword, setKeyword] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const q = useSelectableContracts(keyword, open)
  const rows = q.data ?? []

  const close = () => {
    setKeyword('')
    setSelected(null)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={(v) => (v ? onOpenChange(true) : close())}>
      <DialogContent className="grid-cols-[minmax(0,1fr)] gap-0 p-5 sm:max-w-[520px]">
        <DialogHeader className="pb-3">
          <DialogTitle className="text-[15px]">换个项目</DialogTitle>
        </DialogHeader>

        <p className="mb-3 text-[11.5px] leading-[1.6] text-muted-foreground">
          选定后发票挂到该项目名下；收款需在项目页再关联（原系统建议的收款只对原项目有效）。
        </p>

        <div className="relative mb-2">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            autoFocus
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索项目名称或建档号"
            className="h-[32px] pl-8 text-[12.5px]"
          />
        </div>

        {q.isError && (
          <div className="px-2 py-4 text-center text-[12px] text-destructive">
            {errMessage(q.error, '项目列表加载失败')}
            <button type="button" className="ml-1.5 underline underline-offset-3" onClick={() => void q.refetch()}>
              重试
            </button>
          </div>
        )}

        {!q.isError && q.isLoading && (
          <div className="px-2 py-4 text-center text-[12px] text-muted-foreground">正在载入…</div>
        )}

        {!q.isError && !q.isLoading && rows.length === 0 && (
          <div className="px-2 py-4 text-center text-[12px] text-muted-foreground">
            {keyword ? '没有匹配的项目' : '暂无可选项目'}
          </div>
        )}

        {rows.length > 0 && (
          <ul className="max-h-[280px] overflow-y-auto rounded-[8px] border border-border">
            {rows.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => setSelected(c.id)}
                  className={cn(
                    'flex w-full items-center gap-2 border-b border-border/60 px-2.5 py-2 text-left transition-colors last:border-b-0',
                    selected === c.id ? 'bg-secondary' : 'hover:bg-secondary/60',
                  )}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px]">{c.name}</span>
                    <span className="mt-[1px] block text-[10.5px] text-muted-foreground">
                      {c.fee_mode}
                      {c.outstanding_amount ? ` · 尚欠 ${c.outstanding_amount}` : ''}
                      {c.expires_note ? ` · ${c.expires_note}` : ''}
                    </span>
                  </span>
                  {selected === c.id && <span className="flex-none text-[10.5px] text-status-green">已选</span>}
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={close}
            className="ml-auto rounded-[7px] px-3 py-[6px] text-[12px] text-muted-foreground transition-colors hover:text-foreground"
          >
            取消
          </button>
          <button
            type="button"
            disabled={busy || selected == null}
            onClick={() => {
              if (selected == null) return
              onPick(selected)
              close()
            }}
            className={cn(BTN_PRIMARY, 'h-[30px]')}
          >
            挂到该项目
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
