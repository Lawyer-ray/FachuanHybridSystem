import { Loader2, PackagePlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { PackStatus } from '../types'

type Tab = PackStatus

const TABS: { key: Tab; label: string }[] = [
  { key: 'todo', label: '待处理' },
  { key: 'done', label: '已归案' },
  { key: 'filed', label: '不接归档' },
]

/** 页签栏（含各状态计数角标）+ 快捷键提示 + 右上「新建材料包」按钮。 */
export function DeskTabs({
  tab,
  setTab,
  counts,
  uploading,
  onPickFiles,
}: {
  tab: Tab
  setTab: (t: Tab) => void
  counts: Record<Tab, number>
  uploading: boolean
  onPickFiles: () => void
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end gap-4">
      <div className="flex items-center gap-1.5">
        <div className="flex items-center gap-0.5 rounded-[9px] bg-secondary p-[3px]">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                'flex items-center gap-[6px] rounded-[7px] px-[13px] py-[6px] text-[13px] transition-colors',
                tab === t.key
                  ? 'bg-card font-medium text-foreground shadow-sm'
                  : 'text-secondary-foreground hover:text-foreground',
              )}
            >
              {t.label}
              <span className={cn('text-[11.5px] tabular-nums', tab === t.key ? 'text-secondary-foreground' : 'text-muted-foreground')}>
                {counts[t.key]}
              </span>
            </button>
          ))}
        </div>
        <span className="mx-2 hidden h-[18px] w-px bg-zinc-300 sm:block" />
        <div className="hidden items-center gap-2 text-[11.5px] text-muted-foreground sm:flex">
          <kbd className="rounded border border-border bg-card px-1 py-0.5 font-sans">↑↓←→</kbd> 选择
          <kbd className="rounded border border-border bg-card px-1 py-0.5 font-sans">空格</kbd> 打开
          <kbd className="rounded border border-border bg-card px-1 py-0.5 font-sans">X</kbd> 不接
          <span className="text-zinc-300">|</span>
          全部材料都靠手划，机器不猜
        </div>
      </div>
      <div className="ml-auto">
        <Button onClick={onPickFiles} disabled={uploading} size="sm">
          {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PackagePlus className="h-4 w-4" />}
          新建材料包
        </Button>
      </div>
    </div>
  )
}
