import { Link2, Loader2, PackagePlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  DEFAULT_PACK_STAGE,
  PACK_STAGES,
  PREP_SECTIONS,
  isPackStage,
  sectionOf,
  type PrepStage,
  type PrepSection,
} from '../stages'

/**
 * 预处理页头部：**两级**导航 + 右侧全局动作。
 *
 * 一级只有两个：收件箱（外部消息流）与材料包（加工流水线）。材料包之下再按
 * 状态切分（待处理 / 已归案 / 不接归档）。这样层级是「来源 → 加工」两段，
 * 而不是把「收件箱」和三种状态平铺成四个互相不同类的页签。
 *
 * 材料包的三个状态**不用下拉**：下拉会把角标数字藏起来，而这三个数字正是
 * 「今天还有几包没处理」的主要线索，值得一直可见。所以进入材料包区段后，
 * 一级页签右侧并排出现二级状态页签。
 *
 * 动作区固定在页签**之上**的公共头部、所有阶段下都可见：上传即建包，
 * 新包落在「待处理」，所以它在收件箱阶段同样成立。
 */
export function DeskTabs({
  stage,
  setStage,
  counts,
  uploading,
  onPickFiles,
  onOpenShareLinks,
}: {
  stage: PrepStage
  setStage: (s: PrepStage) => void
  counts: Record<PrepStage, number>
  uploading: boolean
  onPickFiles: () => void
  onOpenShareLinks: () => void
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end gap-4">
      <div className="flex flex-wrap items-center gap-1.5">
        {/* 一级：收件箱 / 材料包。材料包某状态下的计数是三个状态之和——
            一级页签回答"这一支里有多少东西"，细分数看右边的二级页签。 */}
        <div className="flex items-center gap-0.5 rounded-[9px] bg-secondary p-[3px]">
          {PREP_SECTIONS.map((sec) => {
            const active = sectionOf(stage) === sec.key
            return (
              <button
                key={sec.key}
                type="button"
                data-testid={`prep-section-${sec.key}`}
                aria-current={active ? 'page' : undefined}
                onClick={() => setStage(sectionToStage(sec.key, stage))}
                className={cn(
                  'flex items-center gap-[6px] rounded-[7px] px-[13px] py-[6px] text-[13px] transition-colors',
                  active
                    ? 'bg-card font-medium text-foreground shadow-sm'
                    : 'text-secondary-foreground hover:text-foreground',
                )}
              >
                {sec.label}
                <span
                  className={cn(
                    'text-[11.5px] tabular-nums',
                    active ? 'text-secondary-foreground' : 'text-muted-foreground',
                  )}
                >
                  {sectionCount(sec.key, counts)}
                </span>
              </button>
            )
          })}
        </div>

        {/* 二级：仅材料包区段出现。作为同级页签而不是下拉——三个角标要一直可见 */}
        {isPackStage(stage) && (
          <div
            data-testid="prep-pack-stages"
            className="flex items-center gap-0.5 rounded-[9px] border border-border p-[3px]"
          >
            {PACK_STAGES.map((p) => (
              <button
                key={p.key}
                type="button"
                data-testid={`prep-stage-${p.key}`}
                aria-current={stage === p.key ? 'page' : undefined}
                onClick={() => setStage(p.key)}
                className={cn(
                  'flex items-center gap-[6px] rounded-[7px] px-[11px] py-[5px] text-[12.5px] transition-colors',
                  stage === p.key
                    ? 'bg-secondary font-medium text-foreground'
                    : 'text-secondary-foreground hover:bg-secondary/60 hover:text-foreground',
                )}
              >
                {p.label}
                <span className="text-[11px] tabular-nums text-muted-foreground">{counts[p.key]}</span>
              </button>
            ))}
          </div>
        )}

        <span className="mx-2 hidden h-[18px] w-px bg-zinc-300 sm:block" />
        <span className="hidden text-[11.5px] text-muted-foreground sm:inline">全部材料都靠手划，机器不猜</span>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <Button onClick={onOpenShareLinks} size="sm" variant="outline">
          <Link2 className="h-4 w-4" />
          客户链接
        </Button>
        <Button onClick={onPickFiles} disabled={uploading} size="sm">
          {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PackagePlus className="h-4 w-4" />}
          新建材料包
        </Button>
      </div>
    </div>
  )
}

/**
 * 点击一级页签时该落到哪个阶段。
 *
 * 收件箱 → 收件箱；材料包 → **保留当前停留的状态**（用户上次在「已归案」
 * 就回「已归案」），没停留过（此刻在收件箱）才落到默认的「待处理」。
 * 不做"记住上次状态"的额外存储：URL 本身就是那个记忆。
 */
function sectionToStage(target: PrepSection, current: PrepStage): PrepStage {
  if (target === 'inbox') return 'inbox'
  return isPackStage(current) ? current : DEFAULT_PACK_STAGE
}

/** 一级页签角标：收件箱取收件箱数，材料包取三态之和（"这一支里共多少包"） */
function sectionCount(section: PrepSection, counts: Record<PrepStage, number>): number {
  if (section === 'inbox') return counts.inbox ?? 0
  return (counts.todo ?? 0) + (counts.done ?? 0) + (counts.filed ?? 0)
}
