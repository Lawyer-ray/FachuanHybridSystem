import { ArrowLeft, Pencil } from 'lucide-react'
import { cn } from '@/lib/utils'

/** 阅读器顶栏（原型 rd-bar）：返回 + 标题/副标题 + 不接/归案。
 *
 *  只有这两个真决策留在这里；「关闭」与返回是同一动作（close），已删。
 *  归案恒可点：没归完类时点击会跳到第一个未归类的段并提示（引导在 Reader），
 *  比禁用按钮 + 猜原因更省一个状态。未归类数是例外状态才出现的琥珀标——
 *  归类完了它就消失，顶栏回归安静。 */
export function ReaderTopBar({
  title,
  subtitle,
  unclassified,
  onBack,
  onReject,
  onAssign,
  onRename,
}: {
  title: string
  subtitle: string
  unclassified: number
  onBack: () => void
  onReject: () => void
  onAssign: () => void
  onRename: () => void
}) {
  return (
    <div className="flex h-[54px] flex-none items-center gap-3 border-b border-border bg-card px-4 max-[760px]:gap-2 max-[760px]:px-2.5">
      {/* 手机只留箭头：「材料预处理」四个字占掉标题的地盘，标题本身更要紧 */}
      <button
        type="button"
        onClick={onBack}
        className="flex h-8 flex-none items-center gap-1.5 rounded-lg px-2 text-[13px] font-medium text-secondary-foreground hover:bg-secondary"
        title="返回列表 (Esc)"
        aria-label="返回材料预处理列表"
      >
        <ArrowLeft className="h-4 w-4" />
        <span className="max-[760px]:hidden">材料预处理</span>
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[13.5px] font-semibold">{title}</span>
          <button
            type="button"
            onClick={onRename}
            className="grid h-[18px] w-[18px] flex-none place-items-center rounded text-secondary-foreground opacity-70 transition-colors hover:bg-secondary hover:opacity-100"
            title="重命名材料包"
            aria-label="重命名材料包"
          >
            <Pencil className="h-3 w-3" />
          </button>
        </div>
        <div className="flex items-center gap-2 truncate text-[11px] text-muted-foreground">
          <span className="truncate">{subtitle}</span>
          {unclassified > 0 && (
            <span className="flex-none rounded-full bg-amber-50 px-1.5 py-px text-[10.5px] font-medium text-amber-700">
              {unclassified} 段未归类
            </span>
          )}
        </div>
      </div>
      <div className="ml-auto flex flex-none items-center gap-2 max-[760px]:gap-1">
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
          onClick={onAssign}
          title="归案：绑定案件后进入办案流程"
          className={cn(
            'flex h-8 flex-none items-center gap-1.5 rounded-lg bg-foreground px-2 text-[13px] font-medium text-background transition-colors hover:bg-zinc-700',
          )}
        >
          归案
        </button>
      </div>
    </div>
  )
}
