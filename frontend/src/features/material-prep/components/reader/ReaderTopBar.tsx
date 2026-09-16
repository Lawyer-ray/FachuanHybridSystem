import { ArrowLeft, X } from 'lucide-react'
import { cn } from '@/lib/utils'

/** 阅读器顶栏（原型 rd-bar）：返回 + 标题/副标题 + 不接/归案/关闭 */
export function ReaderTopBar({
  title,
  subtitle,
  allClassified,
  onBack,
  onReject,
  onAssign,
  onClose,
}: {
  title: string
  subtitle: string
  allClassified: boolean
  onBack: () => void
  onReject: () => void
  onAssign: () => void
  onClose: () => void
}) {
  return (
    <div className="flex h-[54px] flex-none items-center gap-3 border-b border-border bg-card px-4">
      <button
        type="button"
        onClick={onBack}
        className="flex h-8 flex-none items-center gap-1.5 rounded-lg px-2 text-[13px] font-medium text-secondary-foreground hover:bg-secondary"
        title="返回列表 (Esc)"
      >
        <ArrowLeft className="h-4 w-4" />
        材料预处理
      </button>
      <div className="min-w-0">
        <div className="truncate text-[13.5px] font-semibold">{title}</div>
        <div className="truncate text-[11px] text-muted-foreground">{subtitle}</div>
      </div>
      <div className="ml-auto flex flex-none items-center gap-2">
        <button
          type="button"
          onClick={onReject}
          className="flex h-8 flex-none items-center gap-1.5 rounded-lg border border-transparent bg-transparent px-2 text-[13px] font-medium text-secondary-foreground transition-colors hover:border-border hover:bg-secondary"
          title="不接：已归档留痕，未建案"
        >
          不接
        </button>
        <button
          type="button"
          disabled={!allClassified}
          onClick={onAssign}
          title={allClassified ? '归案：绑定案件后进入办案流程' : '先完成拆分与归类'}
          className={cn(
            'flex h-8 flex-none items-center gap-1.5 rounded-lg px-2 text-[13px] font-medium transition-colors',
            allClassified
              ? 'bg-foreground text-background hover:bg-zinc-700'
              : 'cursor-not-allowed border border-transparent bg-transparent text-muted-foreground',
          )}
        >
          归案
        </button>
        <button
          type="button"
          onClick={onClose}
          className="grid h-8 w-8 place-items-center rounded-lg text-secondary-foreground hover:bg-secondary"
          title="关闭 (Esc)"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
